"""応募者一覧ページの巡回と個別ページへの遷移"""

import asyncio
import logging
import re
from urllib.parse import urlparse, urljoin

from playwright.async_api import Page

from src.browser.selectors import ApplicantListSelectors, ApplicantDetailSelectors

logger = logging.getLogger(__name__)


async def collect_applicant_links(page: Page, config: dict) -> list[dict]:
    """応募者一覧から全応募者のリンクと名前を収集する"""
    base_url = config["hrmos"]["base_url"]
    wait_sec = config["scan"].get("wait_between_pages", 2)
    applicants = []
    page_num = 1

    logger.info(f"応募者一覧ページに遷移: {base_url}")
    await page.goto(base_url, wait_until="networkidle")

    while True:
        logger.info(f"ページ {page_num} から応募者を収集中...")

        # 応募者リンクを取得
        links = await page.query_selector_all(ApplicantListSelectors.APPLICANT_LINK)

        for link in links:
            try:
                href = await link.get_attribute("href")
                name_el = await link.query_selector(ApplicantListSelectors.APPLICANT_NAME)
                name = await name_el.inner_text() if name_el else await link.inner_text()
                name = name.strip()

                if href:
                    # 相対URLを絶対URLに変換
                    full_url = urljoin(page.url, href)
                    # URLからIDを抽出（例: /candidates/12345 → 12345）
                    applicant_id = _extract_id_from_url(full_url)

                    if applicant_id:
                        applicants.append({
                            "id": applicant_id,
                            "name": name,
                            "page_url": full_url,
                        })
            except Exception as e:
                logger.warning(f"応募者リンクの解析に失敗: {e}")
                continue

        # 次のページがあるか確認
        has_next = await _go_to_next_page(page)
        if not has_next:
            break

        page_num += 1
        await asyncio.sleep(wait_sec)

    logger.info(f"合計 {len(applicants)} 名の応募者を発見")
    return applicants


async def get_attachment_links(page: Page, applicant_url: str) -> list[dict]:
    """応募者個別ページから添付ファイルリンクを取得する"""
    logger.info(f"応募者ページに遷移: {applicant_url}")
    await page.goto(applicant_url, wait_until="networkidle")

    attachments = []

    # 添付ファイルリンクを探す
    links = await page.query_selector_all(ApplicantDetailSelectors.ATTACHMENT_LINK)

    for link in links:
        try:
            href = await link.get_attribute("href")
            # ファイル名を取得
            name_el = await link.query_selector(ApplicantDetailSelectors.ATTACHMENT_NAME)
            filename = await name_el.inner_text() if name_el else await link.inner_text()
            filename = filename.strip()

            if not filename:
                # hrefからファイル名を推測
                filename = href.split("/")[-1].split("?")[0] if href else "unknown"

            if href:
                full_url = urljoin(page.url, href)
                file_type = _detect_file_type(filename)
                attachments.append({
                    "url": full_url,
                    "filename": filename,
                    "file_type": file_type,
                })
        except Exception as e:
            logger.warning(f"添付ファイルリンクの解析に失敗: {e}")
            continue

    logger.info(f"  添付ファイル {len(attachments)} 件を発見")
    return attachments


async def _go_to_next_page(page: Page) -> bool:
    """次のページに遷移する。次ページがない場合はFalseを返す"""
    try:
        # 次ページボタンが無効かどうか確認
        disabled = await page.query_selector(ApplicantListSelectors.NEXT_PAGE_DISABLED)
        if disabled:
            return False

        # 次ページボタンをクリック
        next_btn = await page.query_selector(ApplicantListSelectors.NEXT_PAGE_BUTTON)
        if not next_btn:
            return False

        await next_btn.click()
        await page.wait_for_load_state("networkidle")
        return True

    except Exception as e:
        logger.debug(f"次ページへの遷移不可: {e}")
        return False


def _extract_id_from_url(url: str) -> str:
    """URLから応募者IDを抽出する"""
    parsed = urlparse(url)
    # パスの最後のセグメントをIDとして使用
    # 例: /candidates/12345 → 12345
    path_parts = [p for p in parsed.path.split("/") if p]
    if path_parts:
        return path_parts[-1]
    # フォールバック: URL全体をIDとして使用
    return url


def _detect_file_type(filename: str) -> str:
    """ファイル名から拡張子を判定する"""
    filename_lower = filename.lower()
    if filename_lower.endswith(".pdf"):
        return "pdf"
    elif filename_lower.endswith(".docx"):
        return "docx"
    elif filename_lower.endswith(".doc"):
        return "doc"
    elif filename_lower.endswith(".xlsx"):
        return "xlsx"
    elif filename_lower.endswith(".xls"):
        return "xls"
    else:
        return "unknown"
