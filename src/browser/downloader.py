"""添付ファイルのダウンロードモジュール"""

import logging
from pathlib import Path

from playwright.async_api import Page

logger = logging.getLogger(__name__)


async def download_file(page: Page, url: str, save_dir: str, filename: str) -> str | None:
    """ファイルをダウンロードして保存パスを返す"""
    save_path = Path(save_dir) / filename

    # 既にダウンロード済みならスキップ
    if save_path.exists():
        logger.info(f"  ダウンロード済み（スキップ）: {filename}")
        return str(save_path)

    # 保存先ディレクトリを作成
    save_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Playwrightのダウンロードイベントを利用
        async with page.expect_download(timeout=30000) as download_info:
            # ダウンロードリンクをクリックまたはナビゲート
            await page.evaluate(f"window.location.href = '{url}'")

        download = await download_info.value
        await download.save_as(str(save_path))
        logger.info(f"  ダウンロード完了: {filename}")
        return str(save_path)

    except Exception:
        # expect_download がうまくいかない場合、直接リクエストで取得
        logger.debug(f"  ダウンロードイベント失敗。直接リクエストで試行: {filename}")
        try:
            response = await page.context.request.get(url)
            if response.ok:
                body = await response.body()
                save_path.write_bytes(body)
                logger.info(f"  ダウンロード完了（直接リクエスト）: {filename}")
                return str(save_path)
            else:
                logger.error(f"  ダウンロード失敗 (HTTP {response.status}): {filename}")
                return None
        except Exception as e2:
            logger.error(f"  ダウンロード失敗: {filename} - {e2}")
            return None
