"""CLIエントリーポイント - HRMOS採用 応募者書類AI評価ツール"""

import argparse
import asyncio
import logging
import sys


def setup_logging(verbose: bool = False):
    """ログ設定"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # サードパーティライブラリのDEBUGログを抑制
    if verbose:
        for noisy_logger in ["pdfminer", "pdfplumber", "PIL", "urllib3", "asyncio"]:
            logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def main():
    parser = argparse.ArgumentParser(
        description="HRMOS採用 応募者書類AI評価ツール"
    )
    parser.add_argument(
        "--config", default="config.yaml",
        help="設定ファイルのパス (デフォルト: config.yaml)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="詳細ログを出力"
    )

    subparsers = parser.add_subparsers(dest="command", help="実行コマンド")

    # scan コマンド
    scan_parser = subparsers.add_parser("scan", help="応募者書類をAI評価する")
    scan_parser.add_argument(
        "--all", action="store_true", dest="rescan_all",
        help="全応募者を再評価（評価済みも含む）"
    )
    scan_parser.add_argument(
        "--retry-errors", action="store_true", dest="retry_errors",
        help="エラー状態の応募者も再評価対象に含める"
    )

    # report コマンド
    report_parser = subparsers.add_parser("report", help="AI評価結果をExcelに出力")
    report_parser.add_argument(
        "--run-id", default=None,
        help="特定のスキャン実行IDの結果のみ出力"
    )

    # status コマンド
    subparsers.add_parser("status", help="評価進捗状況を表示")

    args = parser.parse_args()
    setup_logging(args.verbose)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    from src.main import run_scan, run_report, show_status

    if args.command == "scan":
        asyncio.run(run_scan(args.config, args.rescan_all, args.retry_errors))

    elif args.command == "report":
        run_report(args.config, args.run_id)

    elif args.command == "status":
        show_status(args.config)


if __name__ == "__main__":
    main()
