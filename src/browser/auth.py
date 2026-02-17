"""HRMOS採用の認証モジュール - 2段階ログインとセッション管理"""

import logging
from pathlib import Path

from playwright.async_api import Page, BrowserContext

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

    # ログインページにリダイレクトされていなければセッション有効
    current_url = page.url
    if "login" not in current_url.lower() and "signin" not in current_url.lower():
        logger.info("既存セッションが有効です")
        return True

    # セッションが無効なのでログイン
    logger.info("セッション無効。再ログインします...")
    success = await login(page, config)

    if success:
        await save_session(context)

    return success


async def save_session(context: BrowserContext):
    """セッション状態をファイルに保存"""
    await context.storage_state(path=STORAGE_STATE_PATH)
    logger.info(f"セッション状態を保存: {STORAGE_STATE_PATH}")


def has_saved_session() -> bool:
    """保存済みセッションがあるか確認"""
    return Path(STORAGE_STATE_PATH).exists()
