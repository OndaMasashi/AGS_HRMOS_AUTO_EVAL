"""レポート出力モジュール - CSV/Excel形式でマッチ結果を出力"""

import csv
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

REPORT_HEADERS = [
    "応募者名",
    "応募者ページURL",
    "マッチキーワード",
    "文脈（前後テキスト）",
    "ファイル名",
    "検知日時",
]


def export_csv(matches: list[dict], report_dir: str) -> str:
    """マッチ結果をCSVファイルに出力する"""
    Path(report_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"keyword_matches_{timestamp}.csv"
    filepath = Path(report_dir) / filename

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(REPORT_HEADERS)

        for m in matches:
            writer.writerow([
                m.get("applicant_name", ""),
                m.get("page_url", ""),
                m.get("keyword", ""),
                m.get("context", ""),
                m.get("filename", ""),
                m.get("found_at", ""),
            ])

    logger.info(f"CSVレポート出力: {filepath} ({len(matches)} 件)")
    return str(filepath)


def export_excel(matches: list[dict], report_dir: str) -> str:
    """マッチ結果をExcelファイルに出力する"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    Path(report_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"keyword_matches_{timestamp}.xlsx"
    filepath = Path(report_dir) / filename

    wb = Workbook()
    ws = wb.active
    ws.title = "キーワード検知結果"

    # ヘッダー行のスタイル
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")

    # ヘッダー書き込み
    for col, header in enumerate(REPORT_HEADERS, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    # データ書き込み
    for row_idx, m in enumerate(matches, 2):
        ws.cell(row=row_idx, column=1, value=m.get("applicant_name", ""))
        ws.cell(row=row_idx, column=2, value=m.get("page_url", ""))
        ws.cell(row=row_idx, column=3, value=m.get("keyword", ""))
        ws.cell(row=row_idx, column=4, value=m.get("context", ""))
        ws.cell(row=row_idx, column=5, value=m.get("filename", ""))
        ws.cell(row=row_idx, column=6, value=m.get("found_at", ""))

    # 列幅の自動調整
    col_widths = [20, 50, 15, 60, 30, 20]
    for col, width in enumerate(col_widths, 1):
        ws.column_dimensions[chr(64 + col)].width = width

    wb.save(filepath)
    logger.info(f"Excelレポート出力: {filepath} ({len(matches)} 件)")
    return str(filepath)
