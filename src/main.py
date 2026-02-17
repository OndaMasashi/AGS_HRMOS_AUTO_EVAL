"""メインオーケストレーター - スキャン処理の全体制御"""

import asyncio
import logging
import shutil
from pathlib import Path

from playwright.async_api import async_playwright

from src.browser.auth import ensure_authenticated, has_saved_session, STORAGE_STATE_PATH
from src.browser.navigator import collect_applicant_links, get_attachment_links, download_attachment
from src.config import load_config
from src.database.models import init_db
from src.database.repository import Repository
from src.parser.document import extract_text
from src.scanner.keyword import scan_text
from src.reporter.export import export_csv, export_excel

logger = logging.getLogger(__name__)


async def run_scan(config_path: str = "config.yaml", rescan_all: bool = False):
    """メインスキャン処理を実行"""
    config = load_config(config_path)
    conn = init_db(config["scan"]["db_path"])
    repo = Repository(conn)

    keywords = config["keywords"]
    download_dir = config["scan"]["download_dir"]
    wait_sec = config["scan"].get("wait_between_pages", 2)
    headless = config["scan"].get("headless", False)
    delete_after = config["scan"].get("delete_downloads_after", False)

    logger.info(f"検索キーワード: {keywords}")

    # スキャン実行を開始
    run_id = repo.create_scan_run()
    logger.info(f"スキャン実行開始: {run_id}")

    total_applicants = 0
    scanned_count = 0
    match_count = 0

    try:
        async with async_playwright() as p:
            # ブラウザ起動
            browser_args = {}
            if has_saved_session():
                browser_args["storage_state"] = STORAGE_STATE_PATH

            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(**browser_args)
            page = await context.new_page()

            # 認証
            authenticated = await ensure_authenticated(context, page, config)
            if not authenticated:
                logger.error("認証に失敗しました。処理を中断します。")
                repo.fail_scan_run(run_id)
                return

            # 応募者一覧を収集
            logger.info("応募者一覧を収集中...")
            applicants = await collect_applicant_links(page, config)
            total_applicants = len(applicants)

            # DBに応募者を登録
            for app in applicants:
                repo.upsert_applicant(app["id"], app["name"], app["page_url"])

            # 再スキャンの場合は全員をpendingに戻す
            if rescan_all:
                repo.reset_all_applicants()
                targets = repo.get_all_applicants()
            else:
                targets = repo.get_pending_applicants()

            logger.info(f"スキャン対象: {len(targets)} 名 / 全 {total_applicants} 名")

            # 各応募者を処理
            for i, applicant in enumerate(targets, 1):
                app_id = applicant["id"]
                app_name = applicant["name"]
                app_url = applicant["page_url"]

                logger.info(f"[{i}/{len(targets)}] {app_name} を処理中...")

                try:
                    # 添付ファイル情報を取得
                    attachments = await get_attachment_links(page, app_url)

                    if not attachments:
                        logger.info(f"  添付ファイルなし")
                        repo.mark_applicant_scanned(app_id)
                        scanned_count += 1
                        continue

                    # 各添付ファイルを処理
                    app_download_dir = str(Path(download_dir) / app_id)

                    for att in attachments:
                        # ダウンロード
                        file_path = await download_attachment(
                            page, att["filename"], app_download_dir
                        )
                        if not file_path:
                            continue

                        # テキスト抽出
                        text = extract_text(file_path)
                        if not text:
                            continue

                        # DBにドキュメントを記録
                        doc_id = repo.add_document(
                            app_id, att["filename"], att["file_type"],
                            file_path, len(text)
                        )

                        # キーワード検索
                        matches = scan_text(text, keywords)

                        for m in matches:
                            repo.add_match(
                                app_id, doc_id, m["keyword"],
                                m["context"], run_id
                            )
                            match_count += 1

                    repo.mark_applicant_scanned(app_id)
                    scanned_count += 1

                    # ダウンロードファイル削除（オプション）
                    if delete_after and Path(app_download_dir).exists():
                        shutil.rmtree(app_download_dir)

                except Exception as e:
                    logger.error(f"  応募者 {app_name} の処理でエラー: {e}")
                    repo.mark_applicant_error(app_id)

                # ページ間の待機
                await asyncio.sleep(wait_sec)

            await browser.close()

        # スキャン完了
        repo.complete_scan_run(run_id, total_applicants, scanned_count, match_count)
        logger.info(
            f"スキャン完了: {scanned_count}/{total_applicants} 名処理, "
            f"{match_count} 件のキーワードマッチ"
        )

        # レポート自動出力
        if match_count > 0:
            matches = repo.get_matches_for_run(run_id)
            report_dir = config["scan"]["report_dir"]
            csv_path = export_csv(matches, report_dir)
            xlsx_path = export_excel(matches, report_dir)
            logger.info(f"レポート出力: {csv_path}")
            logger.info(f"レポート出力: {xlsx_path}")

    except Exception as e:
        logger.error(f"スキャン処理で致命的エラー: {e}")
        repo.fail_scan_run(run_id)
        raise
    finally:
        conn.close()


def run_report(config_path: str = "config.yaml", run_id: str | None = None):
    """レポートを出力する"""
    config = load_config(config_path)
    conn = init_db(config["scan"]["db_path"])
    repo = Repository(conn)

    if run_id:
        matches = repo.get_matches_for_run(run_id)
    else:
        matches = repo.get_all_matches()

    if not matches:
        logger.info("マッチ結果がありません。")
        conn.close()
        return

    report_dir = config["scan"]["report_dir"]
    csv_path = export_csv(matches, report_dir)
    xlsx_path = export_excel(matches, report_dir)

    print(f"\nレポート出力完了:")
    print(f"  CSV:   {csv_path}")
    print(f"  Excel: {xlsx_path}")
    print(f"  件数:  {len(matches)} 件")

    conn.close()


def show_status(config_path: str = "config.yaml"):
    """スキャン進捗状況を表示する"""
    config = load_config(config_path)
    conn = init_db(config["scan"]["db_path"])
    repo = Repository(conn)

    # 応募者統計
    stats = repo.get_applicant_stats()
    print("\n=== 応募者スキャン状況 ===")
    print(f"  全応募者:      {stats['total']} 名")
    print(f"  スキャン済み:  {stats['scanned']} 名")
    print(f"  未スキャン:    {stats['pending']} 名")
    print(f"  エラー:        {stats['errors']} 名")

    # 実行履歴
    runs = repo.get_scan_runs(limit=5)
    if runs:
        print("\n=== 直近のスキャン実行履歴 ===")
        for run in runs:
            print(
                f"  [{run['status']}] {run['started_at']} - "
                f"{run['scanned_count']}/{run['total_applicants']} 名, "
                f"{run['match_count']} マッチ"
            )

    conn.close()
