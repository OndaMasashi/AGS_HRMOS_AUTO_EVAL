"""メール通知モジュール - Resendを使用してAI評価結果をメール送信"""

import base64
import json
import logging
import os
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from src.evaluator.prompt_builder import is_first_pass_candidate

try:
    import resend
except ImportError:
    resend = None

logger = logging.getLogger(__name__)


def send_report_email(
    evaluations: list[dict],
    criteria_names: list[str],
    xlsx_path: str,
    config: dict,
    total_applicants: int,
    scanned_count: int,
) -> bool:
    """AI評価結果をメールで送信する

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

    # 応募者ごとにグルーピングして件数算出
    applicant_ids = set(ev["applicant_id"] for ev in evaluations)
    eval_count = len(applicant_ids)

    first_pass_criteria = config.get("first_pass_criteria", [])

    subject = f"{prefix} AI評価完了 {eval_count}名 ({today})"
    html = _build_html(
        evaluations, criteria_names, total_applicants, scanned_count,
        today, first_pass_criteria,
    )

    attachments = []
    xlsx_file = Path(xlsx_path)
    if xlsx_file.exists():
        with open(xlsx_file, "rb") as f:
            content = base64.b64encode(f.read()).decode("utf-8")
        attachments.append({
            "filename": xlsx_file.name,
            "content": content,
        })

    try:
        params = {
            "from": from_addr,
            "to": to_list,
            "subject": subject,
            "html": html,
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
    # 応募者ごとにグルーピング
    by_applicant = OrderedDict()
    for ev in evaluations:
        app_id = ev["applicant_id"]
        if app_id not in by_applicant:
            by_applicant[app_id] = {
                "name": ev.get("applicant_name", "不明"),
                "age": ev.get("applicant_age"),
                "total_score": ev.get("total_score", 0),
                "overall_comment": ev.get("overall_comment", ""),
            }

    eval_count = len(by_applicant)
    criteria_count = len(criteria_names)

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

        applicant_rows += (
            f"<tr>"
            f"<td style='padding: 4px 8px; border: 1px solid #ddd;'>{app_data['name']}</td>"
            f"<td style='padding: 4px 8px; border: 1px solid #ddd; text-align: center;'>{age_display}</td>"
            f"<td style='padding: 4px 8px; border: 1px solid #ddd; text-align: center; {candidate_style}'>{candidate_mark}</td>"
            f"<td style='padding: 4px 8px; border: 1px solid #ddd; text-align: center;'>{avg_score}</td>"
            f"<td style='padding: 4px 8px; border: 1px solid #ddd; text-align: center;'>{app_data['total_score']}</td>"
            f"<td style='padding: 4px 8px; border: 1px solid #ddd;'>{app_data['overall_comment'][:100]}</td>"
            f"</tr>\n"
        )

    return f"""\
<div style="font-family: sans-serif; color: #333; max-width: 800px;">
  <h2 style="color: #2F5496;">{today} HRMOS AI評価結果</h2>
  <table style="border-collapse: collapse; margin: 16px 0;">
    <tr><td style="padding: 4px 12px;">スキャン対象</td><td><strong>{total_applicants}名</strong></td></tr>
    <tr><td style="padding: 4px 12px;">処理済み</td><td><strong>{scanned_count}名</strong></td></tr>
    <tr><td style="padding: 4px 12px;">評価完了</td><td><strong>{eval_count}名</strong></td></tr>
  </table>

  <h3>評価サマリ</h3>
  <table style="border-collapse: collapse; width: 100%;">
    <tr style="background-color: #2F5496; color: white;">
      <th style="padding: 6px 8px; border: 1px solid #ddd;">応募者名</th>
      <th style="padding: 6px 8px; border: 1px solid #ddd;">年齢</th>
      <th style="padding: 6px 8px; border: 1px solid #ddd;">1次通過候補</th>
      <th style="padding: 6px 8px; border: 1px solid #ddd;">平均点</th>
      <th style="padding: 6px 8px; border: 1px solid #ddd;">合計点</th>
      <th style="padding: 6px 8px; border: 1px solid #ddd;">総合評価</th>
    </tr>
    {applicant_rows}
  </table>

  <p style="color: #666; font-size: 13px;">詳細は添付のExcelファイルをご確認ください。</p>
</div>
"""
