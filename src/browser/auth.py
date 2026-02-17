"""HRMOS採用の認証モジュール - ログインとセッション管理"""

import logging
from pathlib import Path

from playwright.async_api import Page, BrowserContext

from src.browser.selectors import LoginSelectors

logger = logging.getLogger(__name__)

STORAGE_STATE_PATH = "storage_state.json"


async def login(page: Page, config: dict) -> bool:
    """HRMOS採用にメール+パスワードでログインする"""
    login_url = config["hrmos"]["login_url"]
    email = config["credentials"]["email"]
    password = config["credentials"]["password"]

    logger.info(f"ログインページに遷移: {login_url}")
    await page.goto(login_url, wait_until="networkidle")

    try:
        # メールアドレス入力
        await page.wait_for_selector(LoginSelectors.EMAIL_INPUT, timeout=10000)
        await page.fill(LoginSelectors.EMAIL_INPUT, email)

        # パスワード入力
        await page.fill(LoginSelectors.PASSWORD_INPUT, password)

        # ログインボタンクリック
        await page.click(LoginSelectors.LOGIN_BUTTON)

        # ログイン成功の確認
        await page.wait_for_selector(
            LoginSelectors.LOGIN_SUCCESS_INDICATOR, timeout=15000
        )
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
        # セッション状態を保存
        await save_session(context)

    return success


async def save_session(context: BrowserContext):
    """セッション状態をファイルに保存"""
    await context.storage_state(path=STORAGE_STATE_PATH)
    logger.info(f"セッション状態を保存: {STORAGE_STATE_PATH}")


def has_saved_session() -> bool:
    """保存済みセッションがあるか確認"""
    return Path(STORAGE_STATE_PATH).exists()
