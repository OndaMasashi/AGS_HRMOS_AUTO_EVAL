"""HRMOS採用の認証モジュール - 2段階ログインとセッション管理"""

import logging
from pathlib import Path

from playwright.async_api import Page, BrowserContext, TimeoutError as PlaywrightTimeoutError

from src.browser.selectors import LoginSelectors

logger = logging.getLogger(__name__)

STORAGE_STATE_PATH = "storage_state.json"


async def login(page: Page, config: dict) -> bool:
    """HRMOS採用に2段階（メール→パスワード）でログインする"""
    login_url = config["hrmos"]["login_url"]
    email = config["credentials"]["email"]
    password = config["credentials"]["password"]

    logger.info(f"ログインページに遷移: {login_url}")
    await page.goto(login_url, wait_until="networkidle")

    try:
        # Step 1: メールアドレス入力 → 「続行」クリック
        email_input = page.get_by_role(
            LoginSelectors.EMAIL_INPUT_ROLE, name=LoginSelectors.EMAIL_INPUT_NAME
        )
        await email_input.wait_for(timeout=10000)
        await email_input.click()
        await email_input.fill(email)

        continue_btn = page.get_by_role("button", name=LoginSelectors.CONTINUE_BUTTON_NAME)
        await continue_btn.click()

        # Step 2: パスワード入力 → 「ログイン」クリック
        password_input = page.get_by_role(
            LoginSelectors.PASSWORD_INPUT_ROLE, name=LoginSelectors.PASSWORD_INPUT_NAME
        )
        await password_input.wait_for(timeout=10000)
        await password_input.fill(password)

        login_btn = page.get_by_role(
            "button", name=LoginSelectors.LOGIN_BUTTON_NAME, exact=True
        )
        await login_btn.click()

        # ログイン成功の確認（URLがloginから変わるのを待つ）
        await page.wait_for_url("**/interviews**", timeout=15000)
        logger.info("ログイン成功")
        return True

    except Exception as e:
        logger.error(f"ログイン失敗: {e}")
        return False


async def ensure_authenticated(context: BrowserContext, page: Page, config: dict) -> bool:
    """認証状態を確保する（セッション再利用 → 再ログイン）"""
    base_url = config["hrmos"]["base_url"]

    # まずセッションが有効か確認（直接アクセスしてみる）
    logger.info("セッション有効性を確認中...")
    await page.goto(base_url, wait_until="networkidle")

    current_url = page.url
    redirected_to_login = (
        "login" in current_url.lower() or "signin" in current_url.lower()
    )

    if not redirected_to_login:
        # URL だけでは「URL は /interviews のままだがデータ取得が未認証で
        # 一覧が空」というセッション失効途中の中間状態を見逃す。応募者一覧が
        # 実際に描画されているかまで確認する。
        if await _applicant_list_rendered(page):
            logger.info("既存セッションが有効です")
            return True
        logger.warning(
            "URL は一覧ページですが応募者一覧が描画されていません"
            "（セッション失効の可能性）。再ログインします..."
        )
    else:
        logger.info("セッション無効。再ログインします...")

    # セッションが無効なのでログイン
    success = await login(page, config)

    if success:
        await save_session(context)

    return success


async def _applicant_list_rendered(page: Page, timeout_ms: int = 8000) -> bool:
    """応募者一覧が実際に描画されているか確認する。

    応募者リンク（/interviews/ 等を含むリンク）または「さらに表示」ボタンの
    出現を待ち、いずれかが存在すれば一覧が描画済みとみなす。描画前のレースに
    対する猶予として最大 timeout_ms 待つ。
    """
    # 応募者個別ページ（/interviews/screening/<id>）のリンクに限定する。
    # 単なる /interviews/ ではナビゲーション等のリンクを誤検知し、失効途中
    # （一覧は空だがメニューは描画される）を見逃す恐れがあるため。
    applicant_link = page.locator(
        'a[href*="/interviews/screening/"], a[href*="/candidates/"], a[href*="/applicants/"]'
    )
    try:
        await applicant_link.first.wait_for(state="attached", timeout=timeout_ms)
        return True
    except PlaywrightTimeoutError:
        pass

    # フォールバック: 「さらに表示」ボタンがあれば一覧は描画されている
    try:
        if await page.get_by_text("さらに表示").count() > 0:
            return True
    except Exception:
        pass

    return False


async def save_session(context: BrowserContext):
    """セッション状態をファイルに保存"""
    await context.storage_state(path=STORAGE_STATE_PATH)
    logger.info(f"セッション状態を保存: {STORAGE_STATE_PATH}")


def has_saved_session() -> bool:
    """保存済みセッションがあるか確認"""
    return Path(STORAGE_STATE_PATH).exists()
