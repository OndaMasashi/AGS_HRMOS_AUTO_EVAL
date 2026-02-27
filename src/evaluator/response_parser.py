"""Claude応答パーサー - JSON形式の評価結果を検証・抽出"""

import json
import logging
import re

logger = logging.getLogger(__name__)


class ParseError(Exception):
    """応答パースエラー"""
    pass


def parse_evaluation_response(raw_response: str, criteria_names: list[str]) -> dict:
    """Claudeの応答からJSON評価結果を抽出・検証する"""
    json_str = _extract_json(raw_response)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ParseError(f"JSONパースエラー: {e}\n応答内容: {raw_response[:500]}")

    _validate_structure(data, criteria_names)

    return data


def _extract_json(text: str) -> str:
    """テキストからJSON部分を抽出する"""
    # Case 1: ```json ... ``` で囲まれている場合
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Case 2: { で始まる最初のJSONオブジェクトを探す
    brace_start = text.find('{')
    if brace_start == -1:
        raise ParseError(f"応答にJSONが見つかりません: {text[:300]}")

    depth = 0
    for i in range(brace_start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[brace_start:i + 1]

    return text[brace_start:]


def _validate_structure(data: dict, criteria_names: list[str]):
    """評価結果の構造を検証する"""
    if not isinstance(data, dict):
        raise ParseError("応答がJSONオブジェクトではありません")

    if "evaluations" not in data:
        raise ParseError("'evaluations' キーが見つかりません")

    evaluations = data["evaluations"]
    if not isinstance(evaluations, list):
        raise ParseError("'evaluations' がリストではありません")

    for eval_item in evaluations:
        if not isinstance(eval_item, dict):
            raise ParseError(f"評価項目がオブジェクトではありません: {eval_item}")

        for required_key in ["criteria_name", "score", "comment"]:
            if required_key not in eval_item:
                raise ParseError(f"評価項目に '{required_key}' がありません: {eval_item}")

        # scoreを整数に正規化
        try:
            score = int(eval_item["score"])
            eval_item["score"] = max(1, min(5, score))
        except (ValueError, TypeError):
            logger.warning(f"  スコアが数値ではありません: {eval_item['score']} → 1に設定")
            eval_item["score"] = 1

    # total_scoreが無い場合は計算
    if "total_score" not in data:
        data["total_score"] = sum(e["score"] for e in evaluations)
    else:
        try:
            data["total_score"] = int(data["total_score"])
        except (ValueError, TypeError):
            data["total_score"] = sum(e["score"] for e in evaluations)

    # overall_commentが無い場合はデフォルト
    if "overall_comment" not in data:
        data["overall_comment"] = ""

    # interview_questionsが無い場合は空リスト
    if "interview_questions" not in data:
        data["interview_questions"] = []
    elif not isinstance(data["interview_questions"], list):
        data["interview_questions"] = []

    # applicant_genderが無い場合はデフォルト
    if "applicant_gender" not in data:
        data["applicant_gender"] = "不明"
    elif data["applicant_gender"] not in ("男性", "女性", "不明"):
        data["applicant_gender"] = "不明"

    # applicant_ageが無い場合はデフォルト
    if "applicant_age" not in data or data["applicant_age"] is None:
        data["applicant_age"] = None
    else:
        try:
            data["applicant_age"] = int(data["applicant_age"])
        except (ValueError, TypeError):
            data["applicant_age"] = None

    # remarksが無い場合はデフォルト
    if "remarks" not in data:
        data["remarks"] = ""
    elif not isinstance(data["remarks"], str):
        data["remarks"] = str(data["remarks"])
