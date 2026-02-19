"""レポート出力モジュール - AI評価結果をExcel形式で出力"""

import json
import logging
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from src.evaluator.prompt_builder import total_to_rank

logger = logging.getLogger(__name__)


def export_evaluation_excel(
    evaluations: list[dict],
    criteria_names: list[str],
    report_dir: str,
    question_count: int = 3,
) -> str:
    """AI評価結果をExcelファイルに出力する

    1行 = 1応募者
    各評価基準について「スコア」「コメント」の2列
    最終列に「合計点」「総合評価」「質問候補1〜3」
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    Path(report_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"ai_evaluation_{timestamp}.xlsx"
    filepath = Path(report_dir) / filename

    wb = Workbook()
    ws = wb.active
    ws.title = "AI評価結果"

    # ヘッダー構築
    headers = ["応募者名", "性別", "年齢", "HRMOS URL", "ファイル名"]
    for criteria in criteria_names:
        headers.append(f"{criteria}(点)")
        headers.append(f"{criteria}(評価)")
    headers.append("合計点")
    headers.append("総合ランク")
    headers.append("総合評価")
    for i in range(1, question_count + 1):
        headers.append(f"質問候補{i}")

    # ランク別の色定義
    rank_colors = {
        "S": PatternFill(start_color="FFD700", end_color="FFD700", fill_type="solid"),  # 金
        "A": PatternFill(start_color="87CEEB", end_color="87CEEB", fill_type="solid"),  # 水色
        "B": PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid"),  # 薄緑
        "C": PatternFill(start_color="FFE4B5", end_color="FFE4B5", fill_type="solid"),  # 薄橙
        "D": PatternFill(start_color="FFB6C1", end_color="FFB6C1", fill_type="solid"),  # 薄赤
    }

    # スタイル定義
    header_font = Font(bold=True, color="FFFFFF", size=10)
    header_fill = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
    score_fill = PatternFill(start_color="D6E4F0", end_color="D6E4F0", fill_type="solid")
    question_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )

    # ヘッダー書き込み
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        cell.border = thin_border

    # 評価結果を応募者ごとにグルーピング
    by_applicant = OrderedDict()
    for ev in evaluations:
        app_id = ev["applicant_id"]
        if app_id not in by_applicant:
            questions = []
            if ev.get("interview_questions"):
                try:
                    questions = json.loads(ev["interview_questions"])
                except (json.JSONDecodeError, TypeError):
                    questions = []

            by_applicant[app_id] = {
                "name": ev["applicant_name"],
                "gender": ev.get("applicant_gender", "不明"),
                "age": ev.get("applicant_age"),
                "page_url": ev["page_url"],
                "filename": ev["filename"],
                "total_score": ev["total_score"],
                "overall_comment": ev["overall_comment"],
                "interview_questions": questions,
                "criteria": {}
            }
        by_applicant[app_id]["criteria"][ev["criteria_name"]] = {
            "score": ev["score"],
            "comment": ev["comment"],
        }

    # データ行書き込み
    for row_idx, (app_id, app_data) in enumerate(by_applicant.items(), 2):
        col = 1

        ws.cell(row=row_idx, column=col, value=app_data["name"]).border = thin_border
        col += 1

        gender_cell = ws.cell(row=row_idx, column=col, value=app_data.get("gender", "不明"))
        gender_cell.alignment = Alignment(horizontal="center")
        gender_cell.border = thin_border
        col += 1

        age_val = app_data.get("age")
        age_cell = ws.cell(row=row_idx, column=col, value=age_val if age_val is not None else "不明")
        age_cell.alignment = Alignment(horizontal="center")
        age_cell.border = thin_border
        col += 1

        ws.cell(row=row_idx, column=col, value=app_data["page_url"]).border = thin_border
        col += 1

        ws.cell(row=row_idx, column=col, value=app_data["filename"]).border = thin_border
        col += 1

        for criteria in criteria_names:
            c_data = app_data["criteria"].get(criteria, {"score": 0, "comment": "未評価"})

            score_cell = ws.cell(row=row_idx, column=col, value=c_data["score"])
            score_cell.fill = score_fill
            score_cell.alignment = Alignment(horizontal="center")
            score_cell.border = thin_border
            col += 1

            comment_cell = ws.cell(row=row_idx, column=col, value=c_data["comment"])
            comment_cell.alignment = Alignment(wrap_text=True, vertical="top")
            comment_cell.border = thin_border
            col += 1

        total_cell = ws.cell(row=row_idx, column=col, value=app_data["total_score"])
        total_cell.font = Font(bold=True)
        total_cell.alignment = Alignment(horizontal="center")
        total_cell.border = thin_border
        col += 1

        # 総合ランク
        rank = total_to_rank(app_data["total_score"], len(criteria_names))
        rank_cell = ws.cell(row=row_idx, column=col, value=rank)
        rank_cell.font = Font(bold=True, size=12)
        rank_cell.alignment = Alignment(horizontal="center", vertical="center")
        rank_cell.border = thin_border
        if rank in rank_colors:
            rank_cell.fill = rank_colors[rank]
        col += 1

        overall_cell = ws.cell(row=row_idx, column=col, value=app_data["overall_comment"])
        overall_cell.alignment = Alignment(wrap_text=True, vertical="top")
        overall_cell.border = thin_border
        col += 1

        questions = app_data.get("interview_questions", [])
        for i in range(question_count):
            q_text = questions[i] if i < len(questions) else ""
            q_cell = ws.cell(row=row_idx, column=col, value=q_text)
            q_cell.fill = question_fill
            q_cell.alignment = Alignment(wrap_text=True, vertical="top")
            q_cell.border = thin_border
            col += 1

    # 列幅設定
    ws.column_dimensions['A'].width = 15  # 応募者名
    ws.column_dimensions['B'].width = 6   # 性別
    ws.column_dimensions['C'].width = 6   # 年齢
    ws.column_dimensions['D'].width = 40  # HRMOS URL
    ws.column_dimensions['E'].width = 25  # ファイル名

    for i in range(len(criteria_names)):
        score_col = get_column_letter(6 + i * 2)
        comment_col = get_column_letter(7 + i * 2)
        ws.column_dimensions[score_col].width = 8
        ws.column_dimensions[comment_col].width = 40

    base_col = 6 + len(criteria_names) * 2
    ws.column_dimensions[get_column_letter(base_col)].width = 10      # 合計点
    ws.column_dimensions[get_column_letter(base_col + 1)].width = 10  # 総合ランク
    ws.column_dimensions[get_column_letter(base_col + 2)].width = 50  # 総合評価

    for i in range(question_count):
        ws.column_dimensions[get_column_letter(base_col + 3 + i)].width = 45

    ws.freeze_panes = "A2"

    wb.save(filepath)
    logger.info(f"AI評価Excelレポート出力: {filepath} ({len(by_applicant)} 名)")
    return str(filepath)
