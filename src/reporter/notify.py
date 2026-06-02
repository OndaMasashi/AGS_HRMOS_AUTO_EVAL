"""メール通知モジュール - Resendを使用してAI評価結果をメール送信"""

import base64
import html
import logging
import os
import re
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from src.evaluator.prompt_builder import is_first_pass_candidate

try:
    import resend
except ImportError:
    resend = None

logger = logging.getLogger(__name__)

# 内訳列のコメントが長すぎる場合の切り詰め文字数
MAX_CRITERIA_COMMENT_CHARS = 150
# 添付合計サイズの上限（base64エンコード後のバイト数で判定。Resendの~40MB制限に安全マージン）
MAX_TOTAL_ATTACHMENT_BYTES = 38 * 1024 * 1024


def _sanitize_filename(name: str) -> str:
    """ファイル名に使えない文字を除去する（日本語は維持、禁則文字・制御文字を _ に置換）"""
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name)
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    return cleaned or "file"


def _build_attachment_name(applicant_name: str, original_name: str, used_names: set[str]) -> str:
    """添付ファイル名を「応募者名_元名」で生成し、衝突時は連番を付与する"""
    base = f"{_sanitize_filename(applicant_name)}_{original_name}"
    if base not in used_names:
        return base
    stem, suffix = Path(base).stem, Path(base).suffix
    i = 2
    while f"{stem}_{i}{suffix}" in used_names:
        i += 1
    return f"{stem}_{i}{suffix}"


def send_report_email(
    evaluations: list[dict],
    criteria_names: list[str],
    xlsx_path: str,
    config: dict,
    total_applicants: int,
    scanned_count: int,
    attachment_sources: list[dict] | None = None,
) -> bool:
    """AI評価結果をメールで送信する

    Args:
        attachment_sources: 添付する経歴書ファイルのリスト。
            各要素は {"applicant_name": str, "file_path": str}。
            1次通過候補(○)の経歴書のみを想定（呼び出し側で抽出済み）。

    Returns:
        True: 送信成功, False: 送信失敗またはスキップ
    """
    email_config = config.get("email", {})

    if not email_config.get("enabled", False):
        logger.info("メール通知は無効です（email.enabled: false）")
        return False

    if resend is None:
        logger.warning("resendパッケージが未インストールです。pip install resend で追加してください。")
        return False

    api_key = os.environ.get("RESEND_API_KEY") or email_config.get("api_key", "")
    if not api_key:
        logger.warning("Resend APIキーが設定されていません。メール送信をスキップします。")
        return False

    resend.api_key = api_key

    from_addr = email_config.get("from", "onboarding@resend.dev")
    to_list = email_config.get("to", [])
    prefix = email_config.get("subject_prefix", "[HRMOS]")

    if not to_list or not to_list[0]:
        logger.warning("メール送信先が設定されていません。メール送信をスキップします。")
        return False

    today = datetime.now().strftime("%Y-%m-%d")

    # 件名用に評価済み応募者の実人数を算出（評価行は1応募者×評価基準数あるため重複排除）
    eval_count = len(set(ev["applicant_id"] for ev in evaluations))

    first_pass_criteria = config.get("first_pass_criteria", [])

    subject = f"{prefix} AI評価完了 {eval_count}名 ({today})"
    html_body = _build_html(
        evaluations, criteria_names, total_applicants, scanned_count,
        today, first_pass_criteria,
    )

    attachments = []
    total_attachment_bytes = 0

    # Excelレポートを添付
    xlsx_file = Path(xlsx_path)
    if xlsx_file.exists():
        content = base64.b64encode(xlsx_file.read_bytes()).decode("utf-8")
        attachments.append({"filename": xlsx_file.name, "content": content})
        total_attachment_bytes += len(content)

    # 1次通過候補(○)の経歴書を添付
    if attachment_sources:
        used_names = {a["filename"] for a in attachments}
        for src in attachment_sources:
            file_path = Path(src["file_path"])
            if not file_path.exists():
                logger.warning(f"添付対象ファイルが見つかりません（スキップ）: {file_path}")
                continue
            try:
                content = base64.b64encode(file_path.read_bytes()).decode("utf-8")
            except OSError as e:
                logger.error(f"添付ファイルの読み込みに失敗（スキップ）: {file_path} - {e}")
                continue
            if total_attachment_bytes + len(content) > MAX_TOTAL_ATTACHMENT_BYTES:
                logger.warning("添付合計サイズが上限に達したため、以降の経歴書添付をスキップしました")
                break
            attach_name = _build_attachment_name(
                src.get("applicant_name", ""), file_path.name, used_names
            )
            attachments.append({"filename": attach_name, "content": content})
            used_names.add(attach_name)
            total_attachment_bytes += len(content)

    try:
        params = {
            "from": from_addr,
            "to": to_list,
            "subject": subject,
            "html": html_body,
        }
        if attachments:
            params["attachments"] = attachments

        result = resend.Emails.send(params)
        logger.info(f"メール送信成功: {result.get('id', 'unknown')} → {to_list}")
        return True
    except Exception as e:
        logger.error(f"メール送信に失敗しました: {e}")
        return False


def _build_html(
    evaluations: list[dict],
    criteria_names: list[str],
    total_applicants: int,
    scanned_count: int,
    today: str,
    first_pass_criteria: list[dict],
) -> str:
    """メール本文のHTMLを生成する"""
    # 応募者ごとにグルーピング（評価基準ごとの点数・コメントも集約）
    by_applicant = OrderedDict()
    for ev in evaluations:
        app_id = ev["applicant_id"]
        if app_id not in by_applicant:
            by_applicant[app_id] = {
                # DB値が None でも html.escape / スライス / 除算でクラッシュしないよう正規化
                "name": ev.get("applicant_name") or "不明",
                "age": ev.get("applicant_age"),
                "page_url": ev.get("page_url") or "",
                "total_score": ev.get("total_score") or 0,
                "overall_comment": ev.get("overall_comment") or "",
                "criteria": {},
            }
        by_applicant[app_id]["criteria"][ev["criteria_name"]] = {
            "score": ev.get("score"),
            "comment": ev.get("comment") or "",
        }

    eval_count = len(by_applicant)
    criteria_count = len(criteria_names)

    # 各評価基準のヘッダー列
    criteria_headers = "".join(
        f"<th style='padding: 6px 8px; border: 1px solid #ddd;'>{html.escape(name)}</th>"
        for name in criteria_names
    )

    applicant_rows = ""
    for app_data in by_applicant.values():
        avg_score = round(app_data['total_score'] / criteria_count, 1) if criteria_count > 0 else 0
        age_display = app_data['age'] if app_data['age'] is not None else "不明"
        candidate_mark = is_first_pass_candidate(avg_score, app_data['age'], first_pass_criteria)
        if candidate_mark == "○":
            candidate_style = "background-color: #90EE90; font-weight: bold;"
        elif candidate_mark == "△":
            candidate_style = "background-color: #FFFACD; font-weight: bold;"
        else:
            candidate_style = ""

        # 「○」はHRMOS応募者ページへのリンクにする（△・空欄はプレーン）
        page_url = app_data.get("page_url") or ""
        if candidate_mark == "○" and page_url:
            mark_html = (
                f"<a href='{html.escape(page_url, quote=True)}' "
                f"style='color: #155724; font-weight: bold;'>○</a>"
            )
        else:
            mark_html = candidate_mark

        # 各評価基準の内訳セル（点数＋コメント）
        criteria_cells = ""
        for name in criteria_names:
            c_data = app_data["criteria"].get(name)
            if c_data is None or c_data.get("score") is None:
                cell_inner = "-"
            else:
                raw_comment = c_data.get("comment") or ""
                if len(raw_comment) > MAX_CRITERIA_COMMENT_CHARS:
                    raw_comment = raw_comment[:MAX_CRITERIA_COMMENT_CHARS] + "…"
                cell_inner = (
                    f"<b>{c_data['score']}</b>"
                    f"<br><span style='font-size: 12px; color: #555;'>{html.escape(raw_comment)}</span>"
                )
            criteria_cells += (
                f"<td style='padding: 4px 8px; border: 1px solid #ddd; "
                f"vertical-align: top; min-width: 120px;'>{cell_inner}</td>"
            )

        applicant_rows += (
            f"<tr>"
            f"<td style='padding: 4px 8px; border: 1px solid #ddd; vertical-align: top;'>{html.escape(app_data['name'])}</td>"
            f"<td style='padding: 4px 8px; border: 1px solid #ddd; text-align: center; vertical-align: top;'>{age_display}</td>"
            f"<td style='padding: 4px 8px; border: 1px solid #ddd; text-align: center; vertical-align: top; {candidate_style}'>{mark_html}</td>"
            f"<td style='padding: 4px 8px; border: 1px solid #ddd; text-align: center; vertical-align: top;'>{avg_score}</td>"
            f"<td style='padding: 4px 8px; border: 1px solid #ddd; text-align: center; vertical-align: top;'>{app_data['total_score']}</td>"
            f"{criteria_cells}"
            f"<td style='padding: 4px 8px; border: 1px solid #ddd; vertical-align: top; min-width: 200px;'>{html.escape(app_data['overall_comment'][:100])}</td>"
            f"</tr>\n"
        )

    return f"""\
<div style="font-family: sans-serif; color: #333;">
  <h2 style="color: #2F5496;">{today} HRMOS AI評価結果</h2>
  <table style="border-collapse: collapse; margin: 16px 0;">
    <tr><td style="padding: 4px 12px;">スキャン対象</td><td><strong>{total_applicants}名</strong></td></tr>
    <tr><td style="padding: 4px 12px;">処理済み</td><td><strong>{scanned_count}名</strong></td></tr>
    <tr><td style="padding: 4px 12px;">評価完了</td><td><strong>{eval_count}名</strong></td></tr>
  </table>

  <h3>評価サマリ</h3>
  <div style="overflow-x: auto;">
  <table style="border-collapse: collapse; font-size: 13px;">
    <tr style="background-color: #2F5496; color: white;">
      <th style="padding: 6px 8px; border: 1px solid #ddd;">応募者名</th>
      <th style="padding: 6px 8px; border: 1px solid #ddd;">年齢</th>
      <th style="padding: 6px 8px; border: 1px solid #ddd;">1次通過候補</th>
      <th style="padding: 6px 8px; border: 1px solid #ddd;">平均点</th>
      <th style="padding: 6px 8px; border: 1px solid #ddd;">合計点</th>
      {criteria_headers}
      <th style="padding: 6px 8px; border: 1px solid #ddd;">総合評価</th>
    </tr>
    {applicant_rows}
  </table>
  </div>

  <p style="color: #666; font-size: 13px;">○をクリックするとHRMOSの応募者ページが開きます。1次通過候補(○)の経歴書を添付しています。詳細は添付のExcelファイルをご確認ください。</p>
</div>
"""
