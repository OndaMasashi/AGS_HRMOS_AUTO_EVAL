"""メール通知モジュール - Resendを使用してスキャン結果をメール送信"""

import base64
import logging
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    import resend
except ImportError:
    resend = None

logger = logging.getLogger(__name__)


def send_report_email(
    matches: list[dict],
    xlsx_path: str,
    config: dict,
    total_applicants: int,
    scanned_count: int,
) -> bool:
    """スキャン結果をメールで送信する

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

    # APIキー（環境変数を優先）
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
    match_count = len(matches)
    subject = f"{prefix} キーワードマッチ {match_count}件検出 ({today})"

    # 本文を組み立て
    html = _build_html(matches, total_applicants, scanned_count, today)

    # 添付ファイル
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
    matches: list[dict],
    total_applicants: int,
    scanned_count: int,
    today: str,
) -> str:
    """メール本文のHTMLを生成する"""
    match_count = len(matches)

    # 応募者ごとにキーワードをグルーピング
    by_applicant = defaultdict(set)
    for m in matches:
        name = m.get("applicant_name", "不明")
        keyword = m.get("keyword", "")
        by_applicant[name].add(keyword)

    applicant_lines = ""
    for name, keywords in by_applicant.items():
        kw_str = ", ".join(sorted(keywords))
        applicant_lines += f"<li><strong>{name}</strong>: {kw_str}</li>\n"

    return f"""\
<div style="font-family: sans-serif; color: #333; max-width: 600px;">
  <h2 style="color: #4472C4;">{today} HRMOSスキャン結果</h2>
  <table style="border-collapse: collapse; margin: 16px 0;">
    <tr><td style="padding: 4px 12px;">スキャン対象</td><td><strong>{total_applicants}名</strong></td></tr>
    <tr><td style="padding: 4px 12px;">処理済み</td><td><strong>{scanned_count}名</strong></td></tr>
    <tr><td style="padding: 4px 12px;">マッチ件数</td><td><strong>{match_count}件</strong></td></tr>
  </table>

  <h3>マッチ一覧</h3>
  <ul>
    {applicant_lines}
  </ul>

  <p style="color: #666; font-size: 13px;">詳細は添付のExcelファイルをご確認ください。</p>
</div>
"""
