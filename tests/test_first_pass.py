"""1次通過判定と応募日時パースのユニットテスト

HRMOS への自動NG評価登録は、この2つの純粋関数の戻り値だけで「誰を不合格に
するか」と「誰に触れてよいか」を決める。実機なしで壊れを検出できるよう、
境界値と読み取り失敗のケースを固定しておく。
"""

from datetime import datetime

from src.browser.evaluation_form import parse_applied_at
from src.evaluator.prompt_builder import classify_first_pass, is_first_pass_candidate


CRITERIA = [
    {"age_range": [25, 29], "min_avg_score": 2.4},
    {"age_range": [55, 59], "min_avg_score": 4.0},
]


# ================================================================
#  classify_first_pass（○/△/×/判定不能）
# ================================================================

class TestClassifyFirstPass:
    def test_threshold_exactly_is_pass(self):
        assert classify_first_pass(2.4, 27, CRITERIA) == "○"

    def test_above_threshold_is_pass(self):
        assert classify_first_pass(5.0, 27, CRITERIA) == "○"

    def test_borderline_lower_bound_is_triangle(self):
        # min_avg_score - 0.3 ちょうどは △
        assert classify_first_pass(2.1, 27, CRITERIA) == "△"

    def test_just_below_triangle_is_reject(self):
        assert classify_first_pass(2.0, 27, CRITERIA) == "×"

    def test_lowest_score_is_reject(self):
        assert classify_first_pass(1.0, 27, CRITERIA) == "×"

    def test_second_age_band_is_used(self):
        assert classify_first_pass(4.0, 57, CRITERIA) == "○"
        assert classify_first_pass(3.0, 57, CRITERIA) == "×"


class TestClassifyFirstPassUndetermined:
    """判定不能（空文字）になるケース

    空文字を不合格と同一視すると、書類から年齢を読めなかっただけの応募者や、
    年齢帯の設定漏れに当たった応募者を、点数と無関係に落とすことになる。
    """

    def test_age_none_is_undetermined(self):
        assert classify_first_pass(5.0, None, CRITERIA) == ""

    def test_age_outside_all_bands_is_undetermined(self):
        # どの age_range にも入らない（設定は 25-29 と 55-59 のみ）
        assert classify_first_pass(5.0, 45, CRITERIA) == ""

    def test_age_below_all_bands_is_undetermined(self):
        assert classify_first_pass(1.0, 20, CRITERIA) == ""

    def test_empty_criteria_is_undetermined(self):
        assert classify_first_pass(5.0, 27, []) == ""

    def test_undetermined_is_distinct_from_reject(self):
        # 判定不能と不合格が同じ値になっていないこと（自動NG登録の前提）
        assert classify_first_pass(1.0, 27, CRITERIA) != classify_first_pass(1.0, None, CRITERIA)


# ================================================================
#  is_first_pass_candidate（既存の呼び出し元との互換）
# ================================================================

class TestIsFirstPassCandidateCompat:
    """Excel の「1次通過候補」列とメール通知は ○/△/空文字の3値を前提にしている"""

    def test_returns_legacy_three_values(self):
        cases = [
            (2.4, 27, "○"),
            (2.1, 27, "△"),
            (2.0, 27, ""),     # × は空文字に落ちる
            (5.0, None, ""),
            (5.0, 45, ""),
        ]
        for avg, age, expected in cases:
            actual = is_first_pass_candidate(avg, age, CRITERIA)
            assert actual == expected, f"avg={avg} age={age}: {actual!r} != {expected!r}"

    def test_never_returns_reject_mark(self):
        for avg in (0.0, 1.0, 2.0, 2.1, 2.4, 5.0):
            assert is_first_pass_candidate(avg, 27, CRITERIA) != "×"


# ================================================================
#  parse_applied_at（応募日時の読み取り）
# ================================================================

class TestParseAppliedAt:
    def test_parses_screen_format(self):
        text = "応募ID: 2300934609982427136 応募日時 2026/9/1 18:22 選考ポジション"
        assert parse_applied_at(text) == datetime(2026, 9, 1, 18, 22)

    def test_parses_zero_padded(self):
        assert parse_applied_at("応募日時 2026/09/01 18:22") == datetime(2026, 9, 1, 18, 22)

    def test_parses_across_newline(self):
        assert parse_applied_at("応募日時\n2026/09/01 18:22") == datetime(2026, 9, 1, 18, 22)

    def test_parses_with_colon(self):
        assert parse_applied_at("応募日時：2026/9/1 18:22") == datetime(2026, 9, 1, 18, 22)

    def test_time_is_optional(self):
        assert parse_applied_at("応募日時 2026/9/1") == datetime(2026, 9, 1, 0, 0)


class TestParseAppliedAtFailures:
    """読み取れない場合は None を返す（呼び出し側は登録しない側に倒す）"""

    def test_impossible_date_returns_none(self):
        assert parse_applied_at("応募日時 2026/13/45 18:22") is None

    def test_missing_label_returns_none(self):
        assert parse_applied_at("2026/9/1 18:22") is None

    def test_no_date_returns_none(self):
        assert parse_applied_at("応募日時 未登録") is None

    def test_empty_returns_none(self):
        assert parse_applied_at("") is None
