"""応募者一覧ページの巡回と個別ページへの遷移（Playwright locator API使用）"""

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

    logger.info(f"応募者一覧ページに遷移: {base_url}")
    await page.goto(base_url, wait_until="networkidle")

    # NOTE: デフォルトでは「評価未入力」のみ表示（軽量）。
    # 「評価入力済」も含めたい場合は下記を有効化（全件読み込みで数分かかる）
    # await _enable_evaluated_filter(page)

    # 「さらに表示」を繰り返しクリックして全応募者を読み込む
    load_round = 1
    while True:
        show_more = page.get_by_text("さらに表示")
        if await show_more.count() == 0:
            break

        try:
            logger.info(f"「さらに表示」をクリック（{load_round}回目）...")
            await show_more.first.click()
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(wait_sec)
            load_round += 1
        except Exception as e:
            logger.debug(f"「さらに表示」のクリック終了: {e}")
            break

    logger.info("全応募者の読み込み完了。リンクを収集中...")

    # 全リンク要素を取得
    applicants = []
    all_links = page.get_by_role(ApplicantListSelectors.APPLICANT_LINK_ROLE)
    link_count = await all_links.count()

    for i in range(link_count):
        link = all_links.nth(i)
        try:
            href = await link.get_attribute("href")
            if not href:
                continue

            if not _is_applicant_link(href):
                continue

            text = await link.inner_text()
            text = text.strip()

            if not text:
                continue

            name = _extract_name_from_link_text(text)
            full_url = urljoin(page.url, href)
            applicant_id = _extract_id_from_url(full_url)

            if applicant_id and name:
                applicants.append({
                    "id": applicant_id,
                    "name": name,
                    "page_url": full_url,
                })

        except Exception as e:
            logger.warning(f"応募者リンクの解析に失敗: {e}")
            continue

    # 重複を除去（IDベース）
    seen_ids = set()
    unique_applicants = []
    for app in applicants:
        if app["id"] not in seen_ids:
            seen_ids.add(app["id"])
            unique_applicants.append(app)

    logger.info(f"合計 {len(unique_applicants)} 名の応募者を発見")
    return unique_applicants


async def get_attachment_links(page: Page, applicant_url: str) -> list[dict]:
    """応募者個別ページから添付ファイル情報を取得する"""
    logger.info(f"応募者ページに遷移: {applicant_url}")
    await page.goto(applicant_url, wait_until="networkidle")

    attachments = []

    # 「履歴書・職務経歴書の確認」リンクをクリックして添付セクションを表示
    try:
        resume_link = page.get_by_role(
            "link", name=ApplicantDetailSelectors.RESUME_SECTION_LINK_TEXT
        )
        resume_count = await resume_link.count()
        logger.debug(f"  「履歴書・職務経歴書の確認」リンク数: {resume_count}")

        if resume_count > 0:
            await resume_link.first.click()
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            logger.debug(f"  遷移後URL: {page.url}")
        else:
            # テキストで探す（role="link"でない場合のフォールバック）
            resume_text = page.get_by_text("履歴書・職務経歴書の確認")
            text_count = await resume_text.count()
            logger.debug(f"  テキスト「履歴書・職務経歴書の確認」要素数: {text_count}")
            if text_count > 0:
                await resume_text.first.click()
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
    except Exception as e:
        logger.warning(f"  履歴書セクションの展開に失敗: {e}")

    # デバッグ: ページ内にファイル拡張子が含まれているか確認
    try:
        page_text = await page.inner_text("body")
        for ext in [".pdf", ".docx", ".xlsx"]:
            if ext.lower() in page_text.lower():
                logger.debug(f"  ページ内に {ext} テキストあり")
    except Exception:
        pass

    # ファイル名テキスト（.pdf / .docx / .xlsx 等）を探す
    # 複数ファイルに対応: 各拡張子で全てのマッチを収集
    seen_filenames = set()
    for ext in [".pdf", ".docx", ".doc", ".xlsx", ".xls"]:
        # 末尾マッチ($)を外し、拡張子を含むテキスト全般にマッチ
        file_elements = page.get_by_text(re.compile(rf"\{ext}", re.IGNORECASE))
        count = await file_elements.count()
        if count > 0:
            logger.debug(f"  {ext} を含む要素数: {count}")

        for i in range(count):
            try:
                el = file_elements.nth(i)
                raw_text = (await el.inner_text()).strip()
                if not raw_text:
                    continue

                # テキスト内からファイル名を抽出（拡張子を含む部分）
                match = re.search(rf'\S+\{ext}', raw_text, re.IGNORECASE)
                if match:
                    filename = match.group().strip()
                else:
                    filename = raw_text

                if filename and filename not in seen_filenames:
                    seen_filenames.add(filename)
                    attachments.append({
                        "filename": filename,
                        "file_type": ext.lstrip(".").lower(),
                        "element_index": i,
                    })
                    logger.debug(f"  ファイル発見: {filename}")
            except Exception:
                continue

    logger.info(f"  添付ファイル {len(attachments)} 件を発見")
    return attachments


async def download_attachment(page: Page, filename: str, save_dir: str) -> str | None:
    """添付ファイルをダウンロードする（ファイル名テキスト付近のDLアイコンをクリック）"""
    from pathlib import Path

    save_path = Path(save_dir) / filename

    # 既にダウンロード済みならスキップ
    if save_path.exists():
        logger.info(f"  ダウンロード済み（スキップ）: {filename}")
        return str(save_path)

    save_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # ファイル名テキスト要素を見つける
        file_text = page.get_by_text(filename)
        if await file_text.count() == 0:
            logger.warning(f"  ファイル名要素が見つからない: {filename}")
            return None

        # ファイル名の近くにあるダウンロードリンク（空テキストのアイコン）を探す
        # 親要素 or 近隣要素からリンクを探す
        parent = file_text.locator("..")
        download_link = parent.get_by_role("link").filter(has_text=re.compile(r"^$"))

        # 親にない場合は、さらに上の階層を探す
        if await download_link.count() == 0:
            grandparent = parent.locator("..")
            download_link = grandparent.get_by_role("link").filter(has_text=re.compile(r"^$"))

        if await download_link.count() == 0:
            # フォールバック: ファイル名テキスト自体をクリック
            logger.debug(f"  DLアイコンが見つからないため、ファイル名をクリック: {filename}")
            async with page.expect_download(timeout=30000) as download_info:
                await file_text.first.click()
            download = await download_info.value
            await download.save_as(str(save_path))
            logger.info(f"  ダウンロード完了: {filename}")
            return str(save_path)

        # ダウンロードアイコンをクリック
        async with page.expect_download(timeout=30000) as download_info:
            await download_link.first.click()

        download = await download_info.value
        await download.save_as(str(save_path))
        logger.info(f"  ダウンロード完了: {filename}")
        return str(save_path)

    except Exception as e:
        logger.error(f"  ダウンロード失敗: {filename} - {e}")
        return None



async def _enable_evaluated_filter(page: Page):
    """フィルタで「評価・コメント入力済」を有効にして全応募者を表示する

    HRMOSの「担当の選考」ページはデフォルトで「評価・コメント入力済」が
    非表示になっているため、フィルタアイコンをクリックしてチェックを入れる。
    """
    try:
        filter_link = page.locator('a.icon-only:has(hrm-icon[icon="filter"])')
        if await filter_link.count() == 0:
            logger.debug("フィルタアイコンが見つからないためスキップ")
            return

        await filter_link.first.click()
        await asyncio.sleep(1)

        # 「評価・コメント入力済」のチェックボックスを探す
        overlay = page.locator('.cdk-overlay-pane')
        if await overlay.count() == 0:
            logger.debug("フィルタオーバーレイが表示されなかったためスキップ")
            return

        # 「評価・コメント入力済」を含むリスト項目のチェックボックスを確認
        evaluated_li = overlay.locator('li').filter(has_text="評価・コメント入力済")
        if await evaluated_li.count() == 0:
            logger.debug("「評価・コメント入力済」項目が見つからないためスキップ")
            # オーバーレイを閉じる
            await page.locator('.cdk-overlay-backdrop').click()
            await asyncio.sleep(0.5)
            return

        # チェックボックスの状態を確認（labelにcheckedクラスがあればON）
        checkbox_label = evaluated_li.locator('label').first
        label_class = await checkbox_label.get_attribute("class") or ""

        if "checked" not in label_class:
            logger.info("フィルタ: 「評価・コメント入力済」を有効化")
            await evaluated_li.first.click()
            await asyncio.sleep(0.5)

            # 「適用」ボタンをクリック
            apply_btn = overlay.locator('button').filter(has_text="適用")
            if await apply_btn.count() > 0:
                await apply_btn.first.click()
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(1)
                logger.info("フィルタ適用完了")
            else:
                logger.warning("「適用」ボタンが見つかりません")
        else:
            logger.debug("「評価・コメント入力済」は既に有効")
            # オーバーレイを閉じる
            await page.locator('.cdk-overlay-backdrop').click()
            await asyncio.sleep(0.5)

    except Exception as e:
        logger.warning(f"フィルタ操作でエラー（処理を続行）: {e}")
        # エラーでもオーバーレイが開いていたら閉じる
        try:
            backdrop = page.locator('.cdk-overlay-backdrop')
            if await backdrop.count() > 0 and await backdrop.first.is_visible():
                await backdrop.first.click()
                await asyncio.sleep(0.5)
        except Exception:
            pass


def _is_applicant_link(href: str) -> bool:
    """応募者ページへのリンクかどうか判定する"""
    href_lower = href.lower()
    # HRMOSの応募者リンクのパターン
    applicant_patterns = [
        "/interviews/",
        "/candidates/",
        "/applicants/",
    ]
    return any(pattern in href_lower for pattern in applicant_patterns)


def _extract_name_from_link_text(text: str) -> str:
    """リンクテキストから応募者名を抽出する

    テキスト例（改行区切り）:
      行1: "書類選考 / 評価未入力"
      行2: "玉井 晴香"           ← 名前
      行3: "/ 成城大学"
      行4: "（日時指定なし）"
    → "玉井 晴香" を抽出
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # 2行目が名前
    if len(lines) >= 2:
        return lines[1]

    # フォールバック: テキスト全体を短く返す
    return text[:30].strip()


def _extract_id_from_url(url: str) -> str:
    """URLから応募者IDを抽出する"""
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]
    if path_parts:
        return path_parts[-1]
    return url
