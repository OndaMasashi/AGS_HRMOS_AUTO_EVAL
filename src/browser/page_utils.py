"""ページ遷移の共通処理 - 一時的な遅延で実行全体が落ちるのを防ぐ"""

import asyncio
import logging

from playwright.async_api import Page

logger = logging.getLogger(__name__)

# 遷移そのもの（DOM 構築まで）の上限
NAV_TIMEOUT_MS = 30000
# 遷移後にネットワークが静まるのを待つ上限。未到達でも処理は続行する
IDLE_TIMEOUT_MS = 20000
# ready_selector を指定したときに要素の出現を待つ既定の上限
READY_TIMEOUT_MS = 15000
# 遷移の試行回数（初回 + リトライ2回）
MAX_ATTEMPTS = 3
# リトライ前の待機秒数。失敗が続くほど間隔を空ける（1回目失敗後 3秒 → 2回目失敗後 6秒）
RETRY_BASE_WAIT_SEC = 3


async def goto_with_retry(
    page: Page,
    url: str,
    *,
    ready_selector: str | None = None,
    ready_timeout_ms: int = READY_TIMEOUT_MS,
) -> None:
    """ページに遷移する（networkidle 未到達を許容し、遷移失敗はリトライする）。

    従来は wait_until="networkidle" の一発勝負だったため、HRMOS 側の一時的な
    遅延や SPA の常時通信で 30 秒を超えると、その回の実行全体が落ちていた。
    ここでは domcontentloaded で遷移を成立させ、networkidle は「待てたら待つ」
    扱いに変える。遷移自体に失敗した場合のみリトライする。

    Args:
        ready_selector: 指定すると、その要素の出現まで追加で待つ。未出現でも
            続行し、それを異常とみなすかの判断は呼び出し側に委ねる。
        ready_timeout_ms: ready_selector の出現を待つ上限（ミリ秒）。

    Raises:
        Exception: MAX_ATTEMPTS 回すべて遷移に失敗した場合、最後の例外をその
            まま送出する（上位の失敗処理でメール通知に載せるため）。
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        except Exception as e:
            # タイムアウトのほかネットワーク断（ERR_INTERNET_DISCONNECTED 等）も
            # 一時的な場合があるため、種類を問わずリトライする。例外の型は原因
            # 切り分け（遅延か回線断か）に効くのでログに残す。
            logger.warning(
                f"ページ遷移に失敗（{attempt}/{MAX_ATTEMPTS} 回目）: {url}"
                f" - {type(e).__name__}: {e}"
            )
            if attempt == MAX_ATTEMPTS:
                logger.error(
                    f"ページ遷移を {MAX_ATTEMPTS} 回試みましたが失敗しました: {url}"
                )
                raise
            await asyncio.sleep(RETRY_BASE_WAIT_SEC * attempt)
        else:
            await _wait_until_ready(page, ready_selector, ready_timeout_ms)
            return


async def _wait_until_ready(
    page: Page,
    ready_selector: str | None,
    ready_timeout_ms: int,
) -> None:
    """遷移後の描画完了を待つ（待ちきれなくても例外にせず警告のみで続行）。

    ここは「待つだけ」の処理なので、時間切れでも SPA のリダイレクトで待機が
    中断されても、実行全体を落とす理由にはならない。本当に致命的な状態（ページ
    が閉じている等）なら後続の要素操作で必ず再発するため、例外の種類は問わず
    握って続行する。ただし原因切り分け用に例外の型はログに残す。

    ログには遷移先として指定した URL ではなく実際に表示されている URL を出す。
    ログイン画面へ飛ばされていた等を、この1行だけで切り分けられるようにするため。
    """
    try:
        await page.wait_for_load_state("networkidle", timeout=IDLE_TIMEOUT_MS)
    except Exception as e:
        logger.warning(
            f"通信が静止しませんでした（{IDLE_TIMEOUT_MS // 1000} 秒待機、続行）: "
            f"{type(e).__name__} / 現在URL: {page.url}"
        )

    if not ready_selector:
        return

    try:
        await page.locator(ready_selector).first.wait_for(
            state="attached", timeout=ready_timeout_ms
        )
    except Exception as e:
        logger.warning(
            f"想定した要素が {ready_timeout_ms // 1000} 秒待っても出現しませんでした"
            f"（続行）: {ready_selector} / {type(e).__name__} / 現在URL: {page.url}"
        )
