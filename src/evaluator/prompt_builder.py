"""評価プロンプト構築 - 設定に基づいてClaude向けプロンプトを生成"""

import json
import logging

from src.evaluator.claude_client import truncate_text

logger = logging.getLogger(__name__)


def total_to_rank(total_score: int, criteria_count: int) -> str:
    """合計点と基準数から総合ランクを算出"""
    if criteria_count == 0:
        return "D"
    avg = total_score / criteria_count
    if avg >= 4.5:
        return "S"
    elif avg >= 3.5:
        return "A"
    elif avg >= 2.5:
        return "B"
    elif avg >= 1.5:
        return "C"
    else:
        return "D"


def is_first_pass_candidate(avg_score: float, age: int | None, first_pass_criteria: list[dict]) -> str:
    """年齢帯ごとの閾値に基づいて1次通過候補を判定する。○/△/空文字を返す"""
    if age is None or not first_pass_criteria:
        return ""
    for criteria in first_pass_criteria:
        age_range = criteria.get("age_range", [0, 100])
        if age_range[0] <= age <= age_range[1]:
            min_score = criteria.get("min_avg_score", 3.0)
            if avg_score >= min_score:
                return "○"
            elif avg_score >= min_score - 0.3:
                return "△"
            return ""
    return ""


def build_evaluation_prompt(
    resume_text: str,
    criteria: list[dict],
    system_instructions: str = "",
    interview_config: dict | None = None,
) -> str:
    """応募者の書類テキストと評価基準からClaude用プロンプトを構築する"""
    safe_text = truncate_text(resume_text)

    # 評価基準をフォーマット
    criteria_text = ""
    for i, c in enumerate(criteria, 1):
        criteria_text += f"{i}. {c['name']}: {c['description']}\n"

    # 面接質問の設定
    question_count = 3
    question_perspective = ""
    if interview_config:
        question_count = interview_config.get("count", 3)
        question_perspective = interview_config.get("perspective", "")

    # JSON出力のスキーマを明示
    output_schema = {
        "applicant_gender": "（男性/女性/不明）",
        "applicant_age": "（年齢の整数、または推定年齢。不明の場合は null）",
        "evaluations": [
            {
                "criteria_name": "（評価基準名）",
                "score": "(1-5の整数)",
                "comment": "（評価コメント）"
            }
        ],
        "total_score": "(各評価のscore合計)",
        "overall_comment": "（総合評価コメント）",
        "interview_questions": [
            f"（面接質問{i+1}）" for i in range(question_count)
        ],
        "remarks": "（評価基準では測れない特記事項。転職回数が多い、ブランク期間がある、特殊な経歴など。該当なしの場合は空文字）"
    }
    schema_str = json.dumps(output_schema, ensure_ascii=False, indent=2)

    # 面接質問の指示
    interview_instruction = f"""
## 面接質問の生成

応募者との面接で聞くべき質問を{question_count}つ生成してください。
"""
    if question_perspective:
        interview_instruction += f"質問の観点:\n{question_perspective}\n"

    prompt = f"""あなたは採用担当の評価アシスタントです。応募者の書類を読み、指定された評価基準に従って評価してください。

{system_instructions}

## 評価基準

{criteria_text}

## スコアリング基準（全応募者に統一適用すること）

以下の基準を全応募者に一貫して厳密に適用してください。主観や印象ではなく、書類に記載された客観的事実のみで判定してください。

| スコア | 基準 |
|--------|------|
| 5 | 卓越: 該当分野で突出した実績・経験がある |
| 4 | 優秀: 十分な実績・経験があり、期待以上のパフォーマンスが見込める |
| 3 | 標準: 一定の実績・経験があり、業務遂行に支障がないレベル |
| 2 | やや不足: 経験が浅い、または実績が限定的 |
| 1 | 不足: 該当する経験・情報がほぼない、または懸念点がある |

判定ルール:
- 書類に該当情報がない場合は必ず score=1 とすること
- 「おそらく〜だろう」等の推測は禁止。書類に明記された事実のみが根拠
- 同じ経験年数・実績レベルであれば必ず同じスコアを付けること
{interview_instruction}
## 出力形式

必ず以下のJSON形式のみを出力してください。JSON以外のテキストは一切出力しないでください。

{schema_str}

## 注意事項
- applicant_genderは書類から読み取れる性別を「男性」「女性」「不明」のいずれかで記載してください
- applicant_ageは書類の生年月日や年齢から判断してください。不明の場合はnullにしてください
- scoreは1〜5の整数で評価してください
- commentは日本語で、スコアの根拠となる具体的事実を含めて記載してください
- overall_commentは強み・弱みの要約と採用推奨度を含めてください
- interview_questionsは応募者の書類内容に基づいた具体的な質問にしてください
- remarksは評価基準に含まれない注目すべき事項を記載してください（転職頻度、ブランク期間、特殊な経歴、特記すべきスキルなど）。該当なしの場合は空文字にしてください
- 出力はJSONのみ。マークダウンのコードブロック（```）で囲まないでください

## 応募者の書類内容

{safe_text}"""

    return prompt
