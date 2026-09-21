"""メインオーケストレーター - AI評価処理の全体制御"""

import asyncio
import logging
import shutil
from collections import Counter, OrderedDict
from pathlib import Path

from playwright.async_api import async_playwright

from src.browser.auth import ensure_authenticated, has_saved_session, STORAGE_STATE_PATH
from src.browser.evaluation_form import (
    submit_ng_evaluation,
    DRY_RUN,
    FAILED,
    FINAL_STATUSES,
    NO_FORM,
    SUBMIT_UNCERTAIN,
    SUBMITTED,
    TOO_OLD,
    UNKNOWN_DATE,
)
from src.browser.navigator import collect_applicant_links, get_attachment_links, download_attachment
from src.config import load_config
from src.database.models import init_db
from src.database.repository import Repository
from src.parser.document import extract_text
from src.evaluator.llm_client import call_llm, LLMClientError
from src.evaluator.pii_masker import PiiMasker
from src.evaluator.prompt_builder import (
    build_evaluation_prompt,
    classify_first_pass,
    is_first_pass_candidate,
)
from src.evaluator.response_parser import parse_evaluation_response, ParseError
from src.reporter.export import export_evaluation_excel
from src.reporter.notify import (
    send_report_email,
    send_no_candidates_email,
    send_failure_email,
)

logger = logging.getLogger(__name__)

# プロジェクトルート（src/main.py から2階層上）。
# documents.file_path が "./data/downloads/..." 相対パスの場合の絶対化基準に使う
# （実行時CWDに依存させないため）。
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ログ表示用のプロバイダー名（config の provider 値 → 人が読む名前）
PROVIDER_LABELS = {
    "claude": "Claude CLI",
    "gemini_api": "Gemini API",
    "gemini": "Gemini CLI",
}

# 評価できなかった応募者の理由（結果メールに出す）
FAIL_NO_TEXT = "書類の文字を読み取れなかった"
FAIL_UNPARSABLE = "AIの応答を評価結果として読めなかった（評価を断った可能性）"
FAIL_LLM = "AIの呼び出しに失敗した"
FAIL_OTHER = "処理中にエラーが発生した"

# 自動NG評価登録の集計ラベル（表示順）。evaluation_form の結果コードに
# 「登録を試みるまでもなく対象外だった」ケースを足したもの
NG_UNDETERMINED = "undetermined"  # 年齢から判定できず（年齢不明・年齢帯外）
NG_ALREADY = "already"            # 前回までに処理済み
NG_OVER_LIMIT = "over_limit"      # max_per_run に達したため未処理

NG_RESULT_LABELS = {
    SUBMITTED: "登録",
    DRY_RUN: "dry-run確認",
    TOO_OLD: "対象期間外",
    NO_FORM: "評価フォームなし",
    UNKNOWN_DATE: "応募日時不明",
    FAILED: "失敗",
    SUBMIT_UNCERTAIN: "要確認（登録できたか不明）",
    NG_UNDETERMINED: "判定不能",
    NG_ALREADY: "処理済み",
    NG_OVER_LIMIT: "上限超過",
}


def _resolve_download_path(file_path: str) -> Path:
    """書類のローカルパスを絶対化する（相対パスはプロジェクトルート基準で解決）"""
    p = Path(file_path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p.resolve()


def _notify_failure(config: dict, reason: str, total_applicants: int = 0) -> None:
    """スキャン失敗アラートを送信する（通知自体の失敗は本処理を止めないよう握り潰す）"""
    try:
        send_failure_email(config, reason, total_applicants)
    except Exception as e:
        logger.error(f"失敗通知メールでエラー: {e}")


def _collect_first_pass_attachments(
    repo: Repository,
    evaluations: list[dict],
    criteria_names: list[str],
    first_pass_criteria: list[dict],
) -> list[dict]:
    """1次通過候補(○)の応募者の経歴書ファイルを収集する

    評価結果を応募者ごとにグルーピングし、平均点と年齢から○候補を判定。
    ○候補のみ、その応募者の全書類のローカルパスを返す。
    （evaluations のJOINは最後の1書類しか指さないため、documentsを別途引く）
    再評価で蓄積した重複書類は同一パスを除外する。

    Returns:
        list[{"applicant_name": str, "file_path": str}]（絶対パス・重複排除済み）
    """
    criteria_count = len(criteria_names)
    if criteria_count == 0:
        return []

    # 応募者ごとに代表情報を集約（値が None でも安全な既定値に正規化）
    by_applicant = OrderedDict()
    for ev in evaluations:
        app_id = ev["applicant_id"]
        if app_id not in by_applicant:
            by_applicant[app_id] = {
                "name": ev.get("applicant_name") or "不明",
                "age": ev.get("applicant_age"),
                "total_score": ev.get("total_score") or 0,
            }

    attachment_sources = []
    seen_paths = set()
    for app_id, app_data in by_applicant.items():
        avg_score = round(app_data["total_score"] / criteria_count, 1)
        if is_first_pass_candidate(avg_score, app_data["age"], first_pass_criteria) != "○":
            continue
        for doc in repo.get_documents_for_applicant(app_id):
            file_path = doc.get("file_path")
            if not file_path:
                continue
            resolved = str(_resolve_download_path(file_path))
            if resolved in seen_paths:
                continue  # 再評価で蓄積した重複書類を除外
            seen_paths.add(resolved)
            attachment_sources.append({
                "applicant_name": app_data["name"],
                "file_path": resolved,
            })

    return attachment_sources


def _unmask_evaluation_data(data: dict, masker: PiiMasker) -> None:
    """評価結果内のプレースホルダーを元のPIIに復元する"""
    for eval_item in data.get("evaluations", []):
        if "comment" in eval_item:
            eval_item["comment"] = masker.unmask(eval_item["comment"])

    if "overall_comment" in data:
        data["overall_comment"] = masker.unmask(data["overall_comment"])

    if "interview_questions" in data and isinstance(data["interview_questions"], list):
        data["interview_questions"] = [
            masker.unmask(q) if isinstance(q, str) else q
            for q in data["interview_questions"]
        ]

    if "remarks" in data:
        data["remarks"] = masker.unmask(data["remarks"])


def _resolve_ng_config(config: dict, rescan_all: bool, dry_run_flag: bool) -> dict | None:
    """自動NG評価登録の設定を解決する。無効なら None を返す

    dry_run は「config が true」または「--dry-run 指定」のどちらかで有効になる。
    コマンドラインからは安全側にしか倒せない（危険側への上書きはできない）。
    """
    ng_config = config.get("hrmos_evaluation", {})
    # 通常は load_config の検証で弾かれるが、書き方を誤った設定で
    # 例外を出して実行全体を止めないようにする
    if not isinstance(ng_config, dict) or not ng_config.get("enabled"):
        return None

    if rescan_all:
        # --all は全応募者が対象になるため、意図しない大量登録を防ぐ
        logger.warning(
            "--all の実行では HRMOS への自動NG評価登録を行いません"
            "（全応募者が対象となり、意図しない大量登録につながるため）"
        )
        return None

    resolved = {
        # config に dry_run が無い古い config.yaml で有効化された場合に備えて
        # 既定は True（登録しない側）にする
        "dry_run": bool(ng_config.get("dry_run", True)) or dry_run_flag,
        "max_per_run": ng_config.get("max_per_run", 20),
        "max_age_days": ng_config.get("max_age_days", 3),
        "comment": ng_config.get("comment", "自動評価"),
    }
    mode = "dry-run（登録しません）" if resolved["dry_run"] else "本番登録"
    logger.info(
        f"HRMOS自動NG評価登録: 有効 / {mode} / 上限 {resolved['max_per_run']}件 / "
        f"応募 {resolved['max_age_days']}日以内"
    )
    return resolved


async def _run_ng_evaluation(
    page,
    repo: Repository,
    applicant: dict,
    evaluation_data: dict,
    criteria_names: list[str],
    first_pass_criteria: list[dict],
    ng_config: dict,
    ng_stats: Counter,
    ng_processed: int,
    config: dict,
) -> bool:
    """1次通過候補が○にならなかった応募者を HRMOS 上でNG評価にする（1名分）

    Args:
        ng_processed: この実行で既に HRMOS へアクセスした件数（上限判定に使う）

    Returns:
        上限件数に数えるべき操作（登録・dry-run確認）を行ったら True
    """
    app_id = applicant["id"]
    app_name = applicant["name"]

    criteria_count = len(criteria_names)
    if criteria_count == 0:
        return False

    avg_score = round(evaluation_data.get("total_score", 0) / criteria_count, 1)
    mark = classify_first_pass(
        avg_score, evaluation_data.get("applicant_age"), first_pass_criteria
    )

    if mark == "○":
        return False

    if mark == "":
        # 年齢を読めなかった、または年齢帯の設定範囲外。点数で落ちたわけでは
        # ないため、不合格として扱わない
        logger.info(f"  NG登録の対象外（年齢から判定できないため）: {app_name}")
        ng_stats[NG_UNDETERMINED] += 1
        return False

    previous = repo.get_hrmos_eval_status(app_id)
    if previous in FINAL_STATUSES:
        logger.info(f"  NG登録はスキップ（前回 {previous} で確定済み）: {app_name}")
        ng_stats[NG_ALREADY] += 1
        return False

    # 上限の判定は「登録対象だ」と分かってから行う。これより手前に置くと、
    # ○ や判定不能でそもそも登録しない応募者まで上限超過に数えてしまう
    if ng_processed >= ng_config["max_per_run"]:
        logger.info(
            f"  NG登録はスキップ（1回あたりの上限 {ng_config['max_per_run']}件に到達）: {app_name}"
        )
        ng_stats[NG_OVER_LIMIT] += 1
        return False

    status, applied_at = await submit_ng_evaluation(
        page,
        applicant["page_url"],
        ng_config["comment"],
        max_age_days=ng_config["max_age_days"],
        dry_run=ng_config["dry_run"],
        config=config,
    )
    repo.mark_hrmos_eval(app_id, status, applied_at)
    ng_stats[status] += 1
    return status in (SUBMITTED, DRY_RUN)


def _format_ng_summary(ng_stats: Counter, ng_config: dict | None) -> str:
    """自動NG評価登録の結果を1行にまとめる（ログとメール本文で共用）"""
    if ng_config is None:
        return ""

    parts = [
        f"{label} {ng_stats[key]}件"
        for key, label in NG_RESULT_LABELS.items()
        if ng_stats[key]
    ]
    if not parts:
        return "HRMOS自動NG登録: 対象者はいませんでした"

    summary = "HRMOS自動NG登録: " + " / ".join(parts)
    if ng_config["dry_run"]:
        summary += "　※dry-run のため実際には登録していません"
    if ng_stats[FAILED]:
        summary += "　※失敗があります。data/debug/ の画面とログを確認してください"
    if ng_stats[SUBMIT_UNCERTAIN]:
        summary += (
            "　※登録できたか確認できなかった応募者がいます。"
            "二重登録を避けるため再試行しません。HRMOSの選考タイムラインを確認してください"
        )
    return summary


async def run_scan(
    config_path: str = "config.yaml",
    rescan_all: bool = False,
    retry_errors: bool = False,
    dry_run: bool = False,
):
    """メインスキャン処理を実行"""
    config = load_config(config_path)
    conn = init_db(config["scan"]["db_path"])
    repo = Repository(conn)

    criteria = config["evaluation_criteria"]
    criteria_names = [c["name"] for c in criteria]
    interview_config = config.get("interview_questions", {})
    download_dir = config["scan"]["download_dir"]
    wait_sec = config["scan"].get("wait_between_pages", 2)
    headless = config["scan"].get("headless", False)
    delete_after = config["scan"].get("delete_downloads_after", False)

    # 1次通過の判定基準はレポート出力と HRMOS への自動NG登録の両方で使う
    first_pass_criteria = config.get("first_pass_criteria", [])
    ng_config = _resolve_ng_config(config, rescan_all, dry_run)
    ng_stats = Counter()
    # max_per_run に数える件数。dry-run 確認も HRMOS へのアクセスを伴うため含める
    ng_processed = 0

    logger.info(f"評価基準: {criteria_names}")

    # スキャン実行を開始
    run_id = repo.create_scan_run()
    logger.info(f"評価実行開始: {run_id}")

    total_applicants = 0
    scanned_count = 0
    eval_count = 0
    # 今回評価できなかった応募者。status='error' は通常の scan で再試行されず、
    # 1人でも評価に成功すると失敗アラートも出ないため、結果メールに載せないと
    # 誰にも気づかれずに残る（2026-09-16/17 に HRMOS のリマインダーで初めて発覚した）
    failed_applicants: list[dict] = []

    try:
        async with async_playwright() as p:
            # ブラウザ起動
            browser_args = {}
            if has_saved_session():
                browser_args["storage_state"] = STORAGE_STATE_PATH

            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(**browser_args)
            page = await context.new_page()

            # 認証
            authenticated = await ensure_authenticated(context, page, config)
            if not authenticated:
                logger.error("認証に失敗しました。処理を中断します。")
                repo.fail_scan_run(run_id)
                _notify_failure(config, "HRMOSのログイン／セッション認証に失敗しました")
                return

            # 応募者一覧を収集
            logger.info("応募者一覧を収集中...")
            applicants = await collect_applicant_links(page, config)
            total_applicants = len(applicants)

            # DBに応募者を登録
            for app in applicants:
                repo.upsert_applicant(app["id"], app["name"], app["page_url"])

            # 再スキャンの場合は全員をpendingに戻す
            if rescan_all:
                repo.reset_all_applicants()
                targets = repo.get_all_applicants()
            elif retry_errors:
                targets = repo.get_retryable_applicants()
            else:
                targets = repo.get_pending_applicants()

            logger.info(f"評価対象: {len(targets)} 名 / 全 {total_applicants} 名")

            # 各応募者を処理
            for i, applicant in enumerate(targets, 1):
                app_id = applicant["id"]
                app_name = applicant["name"]
                app_url = applicant["page_url"]

                logger.info(f"[{i}/{len(targets)}] {app_name} を処理中...")

                # 再評価時は旧データを削除
                if rescan_all:
                    repo.delete_evaluations_for_applicant(app_id)

                # 前の応募者の応答を失敗時のログに出さないよう、毎回空に戻す
                raw_response = ""
                try:
                    # 添付ファイル情報を取得
                    attachments = await get_attachment_links(page, app_url)

                    if not attachments:
                        logger.info(f"  添付ファイルなし")
                        repo.mark_applicant_scanned(app_id)
                        scanned_count += 1
                        continue

                    # 各添付ファイルを処理し、テキストを結合
                    app_download_dir = str(Path(download_dir) / app_id)
                    all_texts = []
                    last_doc_id = None

                    for att in attachments:
                        # ダウンロード
                        file_path = await download_attachment(
                            page, att["filename"], app_download_dir
                        )
                        if not file_path:
                            continue

                        # テキスト抽出
                        text = extract_text(file_path)
                        if not text:
                            continue

                        # DBにドキュメントを記録
                        doc_id = repo.add_document(
                            app_id, att["filename"], att["file_type"],
                            file_path, len(text)
                        )
                        last_doc_id = doc_id
                        all_texts.append(text)

                    # テキストが抽出できた場合、AI評価を実行
                    combined_text = "\n\n---\n\n".join(all_texts)

                    if not combined_text or last_doc_id is None:
                        logger.warning(f"  テキスト抽出失敗 ({app_name}): 書類はあるがテキストを取得できず")
                        repo.mark_applicant_error(app_id)
                        failed_applicants.append(
                            {"name": app_name, "page_url": app_url, "reason": FAIL_NO_TEXT}
                        )
                        continue

                    # PIIマスキング: LLM送信前に個人情報をプレースホルダーに置換
                    try:
                        masker = PiiMasker(applicant_name=app_name)
                        masked_text = masker.mask(combined_text)
                        if masker.masked_count > 0:
                            logger.info(f"  PIIマスキング完了: {masker.mapping_summary}")
                    except Exception as e:
                        logger.warning(f"  PIIマスキングでエラー（マスクなしで続行）: {e}")
                        masker = PiiMasker(applicant_name="")
                        masked_text = combined_text

                    prompt = build_evaluation_prompt(
                        resume_text=masked_text,
                        criteria=criteria,
                        system_instructions=config.get("evaluation", {}).get("system_instructions", ""),
                        interview_config=interview_config,
                    )

                    provider = config.get("evaluation", {}).get("provider", "claude")
                    logger.info(f"  {PROVIDER_LABELS.get(provider, provider)}で評価中...")
                    raw_response = call_llm(prompt, config)

                    evaluation_data = parse_evaluation_response(raw_response, criteria_names)

                    # PIIアンマスキング: LLM応答内のプレースホルダーを復元
                    _unmask_evaluation_data(evaluation_data, masker)

                    repo.add_evaluations_batch(
                        app_id, last_doc_id, evaluation_data, run_id, raw_response
                    )
                    eval_count += 1
                    logger.info(
                        f"  評価完了: 合計 {evaluation_data['total_score']} 点"
                    )

                    # HRMOS への自動NG評価登録（有効時のみ）。
                    # ここでの失敗を外側の except に渡すと mark_applicant_error に
                    # なり、--retry-errors で LLM を呼び直して二重に課金される。
                    # AI評価は成功しているので、内側で握って警告に留める。
                    if ng_config is not None:
                        try:
                            counted = await _run_ng_evaluation(
                                page, repo, applicant, evaluation_data,
                                criteria_names, first_pass_criteria,
                                ng_config, ng_stats, ng_processed, config,
                            )
                            if counted:
                                ng_processed += 1
                        except Exception as e:
                            logger.error(
                                f"  HRMOSへのNG登録でエラー"
                                f"（AI評価の結果は保存済み）: {type(e).__name__}: {e}"
                            )
                            ng_stats[FAILED] += 1

                    repo.mark_applicant_scanned(app_id)
                    scanned_count += 1

                    # ダウンロードファイル削除（オプション）
                    if delete_after and Path(app_download_dir).exists():
                        shutil.rmtree(app_download_dir)

                except (LLMClientError, ParseError) as e:
                    logger.error(f"  AI評価エラー ({app_name}): {e}")
                    if isinstance(e, ParseError) and raw_response:
                        # ParseError のメッセージは応答の先頭300字で切れる。AI が評価を
                        # 断ったときの理由を後から読めるよう全文を残す（Claude CLI は
                        # 会話を保存しない設定で呼んでいるため、ここが唯一の記録になる）
                        logger.error(f"  AIの応答全文 ({app_name}):\n{raw_response}")
                    repo.mark_applicant_error(app_id)
                    reason = FAIL_UNPARSABLE if isinstance(e, ParseError) else FAIL_LLM
                    failed_applicants.append(
                        {"name": app_name, "page_url": app_url, "reason": reason}
                    )

                except Exception as e:
                    logger.error(f"  応募者 {app_name} の処理でエラー: {e}")
                    repo.mark_applicant_error(app_id)
                    failed_applicants.append(
                        {"name": app_name, "page_url": app_url, "reason": FAIL_OTHER}
                    )

                # ページ間の待機
                await asyncio.sleep(wait_sec)

            await browser.close()

        # 応募者一覧を1件も取得できなかった場合は実質失敗として扱う
        # （ログイン済みでも、セレクタ崩れ・HRMOS表示異常で 0 件になり得る）。
        if total_applicants == 0:
            logger.error("応募者一覧を1件も取得できませんでした。")
            repo.fail_scan_run(run_id)
            _notify_failure(
                config,
                "応募者一覧を1件も取得できませんでした（ログイン状態・HRMOS表示・セレクタを要確認）",
                total_applicants,
            )
            return

        # スキャン完了
        repo.complete_scan_run(run_id, total_applicants, scanned_count, eval_count)
        logger.info(
            f"評価完了: {scanned_count}/{total_applicants} 名処理, "
            f"{eval_count} 名のAI評価完了"
        )

        ng_summary = _format_ng_summary(ng_stats, ng_config)
        if ng_summary:
            logger.info(ng_summary)

        # レポート自動出力
        if eval_count > 0:
            evaluations = repo.get_evaluations_for_run(run_id)
            report_dir = config["scan"]["report_dir"]
            question_count = interview_config.get("count", 3)
            xlsx_path = export_evaluation_excel(
                evaluations, criteria_names, report_dir, question_count,
                first_pass_criteria=first_pass_criteria,
            )
            logger.info(f"レポート出力: {xlsx_path}")

            # メール通知（1次通過候補の経歴書を添付）
            try:
                attachment_sources = None
                if config.get("email", {}).get("attach_resumes", True):
                    attachment_sources = _collect_first_pass_attachments(
                        repo, evaluations, criteria_names, first_pass_criteria
                    )
                send_report_email(
                    evaluations, criteria_names, xlsx_path, config,
                    total_applicants, scanned_count,
                    attachment_sources=attachment_sources,
                    ng_summary=ng_summary,
                    failed_applicants=failed_applicants,
                )
            except Exception as e:
                logger.error(f"メール通知でエラー: {e}")
        elif not targets:
            # 評価対象が真に0件（新規応募者なし）で正常終了 → 「新規なし」を通知
            # （無音による「失敗したのでは」という誤認を防ぐ）
            try:
                send_no_candidates_email(config, total_applicants, scanned_count)
            except Exception as e:
                logger.error(f"新規0件通知メールでエラー: {e}")
        else:
            # 評価対象はいたが1件も評価成功しなかった（全員エラー or 添付書類なし）。
            # 「新規なし」と誤報すると障害が隠れるため、失敗アラートに振り分ける。
            logger.error(
                f"評価対象 {len(targets)} 名を処理しましたが、AI評価成功は0件でした。"
            )
            failure_reason = (
                f"評価対象 {len(targets)} 名を処理しましたが、AI評価に成功した応募者が0名でした"
                f"（全員エラー、または添付書類なし）。LLM CLI・添付取得・書類解析を要確認"
            )
            failed_names = "、".join(failed["name"] for failed in failed_applicants)
            if failed_names:
                failure_reason += f"。評価できなかった応募者: {failed_names}"
            _notify_failure(config, failure_reason, total_applicants)

    except Exception as e:
        logger.error(f"評価処理で致命的エラー: {e}")
        repo.fail_scan_run(run_id)
        _notify_failure(config, f"処理中に例外が発生しました: {e}")
        raise
    finally:
        conn.close()


def run_report(config_path: str = "config.yaml", run_id: str | None = None):
    """レポートを出力する"""
    config = load_config(config_path)
    conn = init_db(config["scan"]["db_path"])
    repo = Repository(conn)

    criteria = config["evaluation_criteria"]
    criteria_names = [c["name"] for c in criteria]
    interview_config = config.get("interview_questions", {})
    question_count = interview_config.get("count", 3)

    if run_id:
        evaluations = repo.get_evaluations_for_run(run_id)
    else:
        evaluations = repo.get_all_evaluations()

    if not evaluations:
        logger.info("評価結果がありません。")
        conn.close()
        return

    report_dir = config["scan"]["report_dir"]
    first_pass_criteria = config.get("first_pass_criteria", [])
    xlsx_path = export_evaluation_excel(
        evaluations, criteria_names, report_dir, question_count,
        first_pass_criteria=first_pass_criteria,
    )

    print(f"\nレポート出力完了:")
    print(f"  Excel: {xlsx_path}")
    print(f"  評価者数: {len(set(ev['applicant_id'] for ev in evaluations))} 名")

    conn.close()


def show_status(config_path: str = "config.yaml"):
    """スキャン進捗状況を表示する"""
    config = load_config(config_path)
    conn = init_db(config["scan"]["db_path"])
    repo = Repository(conn)

    # 応募者統計
    stats = repo.get_applicant_stats()
    print("\n=== 応募者評価状況 ===")
    print(f"  全応募者:      {stats['total']} 名")
    print(f"  評価済み:      {stats['scanned']} 名")
    print(f"  未評価:        {stats['pending']} 名")
    print(f"  エラー:        {stats['errors']} 名")

    # 実行履歴
    runs = repo.get_scan_runs(limit=5)
    if runs:
        print("\n=== 直近の評価実行履歴 ===")
        for run in runs:
            print(
                f"  [{run['status']}] {run['started_at']} - "
                f"{run['scanned_count']}/{run['total_applicants']} 名, "
                f"{run['match_count']} 名評価完了"
            )

    conn.close()
