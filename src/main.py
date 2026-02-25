"""メインオーケストレーター - AI評価処理の全体制御"""

import asyncio
import logging
import shutil
from pathlib import Path

from playwright.async_api import async_playwright

from src.browser.auth import ensure_authenticated, has_saved_session, STORAGE_STATE_PATH
from src.browser.navigator import collect_applicant_links, get_attachment_links, download_attachment
from src.config import load_config
from src.database.models import init_db
from src.database.repository import Repository
from src.parser.document import extract_text
from src.evaluator.llm_client import call_llm, LLMClientError
from src.evaluator.prompt_builder import build_evaluation_prompt
from src.evaluator.response_parser import parse_evaluation_response, ParseError
from src.reporter.export import export_evaluation_excel
from src.reporter.notify import send_report_email

logger = logging.getLogger(__name__)


async def run_scan(config_path: str = "config.yaml", rescan_all: bool = False, retry_errors: bool = False):
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

    logger.info(f"評価基準: {criteria_names}")

    # スキャン実行を開始
    run_id = repo.create_scan_run()
    logger.info(f"評価実行開始: {run_id}")

    total_applicants = 0
    scanned_count = 0
    eval_count = 0

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
                        continue

                    prompt = build_evaluation_prompt(
                        resume_text=combined_text,
                        criteria=criteria,
                        system_instructions=config.get("evaluation", {}).get("system_instructions", ""),
                        interview_config=interview_config,
                    )

                    provider = config.get("evaluation", {}).get("provider", "claude")
                    logger.info(f"  {provider.capitalize()} CLIで評価中...")
                    raw_response = call_llm(prompt, config)

                    evaluation_data = parse_evaluation_response(raw_response, criteria_names)

                    repo.add_evaluations_batch(
                        app_id, last_doc_id, evaluation_data, run_id, raw_response
                    )
                    eval_count += 1
                    logger.info(
                        f"  評価完了: 合計 {evaluation_data['total_score']} 点"
                    )

                    repo.mark_applicant_scanned(app_id)
                    scanned_count += 1

                    # ダウンロードファイル削除（オプション）
                    if delete_after and Path(app_download_dir).exists():
                        shutil.rmtree(app_download_dir)

                except (LLMClientError, ParseError) as e:
                    logger.error(f"  AI評価エラー ({app_name}): {e}")
                    repo.mark_applicant_error(app_id)

                except Exception as e:
                    logger.error(f"  応募者 {app_name} の処理でエラー: {e}")
                    repo.mark_applicant_error(app_id)

                # ページ間の待機
                await asyncio.sleep(wait_sec)

            await browser.close()

        # スキャン完了
        repo.complete_scan_run(run_id, total_applicants, scanned_count, eval_count)
        logger.info(
            f"評価完了: {scanned_count}/{total_applicants} 名処理, "
            f"{eval_count} 名のAI評価完了"
        )

        # レポート自動出力
        if eval_count > 0:
            evaluations = repo.get_evaluations_for_run(run_id)
            report_dir = config["scan"]["report_dir"]
            question_count = interview_config.get("count", 3)
            xlsx_path = export_evaluation_excel(
                evaluations, criteria_names, report_dir, question_count
            )
            logger.info(f"レポート出力: {xlsx_path}")

            # メール通知
            try:
                send_report_email(
                    evaluations, criteria_names, xlsx_path, config,
                    total_applicants, scanned_count,
                )
            except Exception as e:
                logger.error(f"メール通知でエラー: {e}")

    except Exception as e:
        logger.error(f"評価処理で致命的エラー: {e}")
        repo.fail_scan_run(run_id)
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
    xlsx_path = export_evaluation_excel(
        evaluations, criteria_names, report_dir, question_count
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
