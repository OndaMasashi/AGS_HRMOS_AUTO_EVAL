"""PiiMasker のユニットテスト"""

import pytest
from src.evaluator.pii_masker import PiiMasker


# ================================================================
#  氏名マスキング
# ================================================================

class TestNameMasking:
    def test_mask_half_width_space(self):
        masker = PiiMasker(applicant_name="山田 太郎")
        result = masker.mask("応募者名: 山田 太郎\n経歴: 10年")
        assert "山田 太郎" not in result
        assert "[NAME_" in result
        assert "経歴: 10年" in result

    def test_mask_full_width_space(self):
        masker = PiiMasker(applicant_name="山田 太郎")
        result = masker.mask("応募者名: 山田\u3000太郎\n")
        assert "山田\u3000太郎" not in result
        assert "[NAME_" in result

    def test_mask_no_space(self):
        masker = PiiMasker(applicant_name="山田 太郎")
        result = masker.mask("応募者名: 山田太郎\n")
        assert "山田太郎" not in result

    def test_multiple_occurrences_same_placeholder(self):
        masker = PiiMasker(applicant_name="山田 太郎")
        text = "山田 太郎の履歴書\n名前: 山田 太郎"
        result = masker.mask(text)
        assert "山田 太郎" not in result
        assert result.count("[NAME_001]") == 2

    def test_empty_name_no_masking(self):
        masker = PiiMasker(applicant_name="")
        text = "応募者名: 山田 太郎"
        result = masker.mask(text)
        assert result == text

    def test_name_not_in_text(self):
        masker = PiiMasker(applicant_name="鈴木 花子")
        text = "応募者名: 山田 太郎"
        result = masker.mask(text)
        assert result == text
        assert masker.masked_count == 0


# ================================================================
#  電話番号マスキング
# ================================================================

class TestPhoneMasking:
    def test_mobile_with_hyphens(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("電話: 090-1234-5678")
        assert "090-1234-5678" not in result
        assert "[PHONE_001]" in result

    def test_landline(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("TEL: 03-1234-5678")
        assert "03-1234-5678" not in result
        assert "[PHONE_" in result

    def test_no_hyphen(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("電話番号: 09012345678")
        assert "09012345678" not in result
        assert "[PHONE_" in result

    def test_multiple_phones(self):
        masker = PiiMasker(applicant_name="")
        text = "携帯: 090-1111-2222 / 自宅: 03-3333-4444"
        result = masker.mask(text)
        assert "090-1111-2222" not in result
        assert "03-3333-4444" not in result
        assert "[PHONE_001]" in result
        assert "[PHONE_002]" in result

    def test_regional_phone(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("TEL: 045-123-4567")
        assert "045-123-4567" not in result


# ================================================================
#  住所マスキング
# ================================================================

class TestAddressMasking:
    def test_chome_banchi_gou(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("東京都渋谷区神宮前1丁目2番3号")
        assert "1丁目2番3号" not in result
        assert "[ADDR_001]" in result
        assert "東京都渋谷区神宮前" in result

    def test_banchi_format(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("大阪府大阪市北区中之島123番地")
        assert "123番地" not in result
        assert "[ADDR_" in result
        assert "大阪府大阪市北区中之島" in result

    def test_banchi_no_format(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("福岡県福岡市中央区天神4番地の2")
        assert "4番地の2" not in result

    def test_with_building_name(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("東京都世田谷区成城1丁目2番3号 ABCマンション101")
        assert "1丁目2番3号" not in result
        assert "ABCマンション101" not in result  # 建物名も番地以降に含まれる


# ================================================================
#  アンマスキング
# ================================================================

class TestUnmasking:
    def test_unmask_single(self):
        masker = PiiMasker(applicant_name="山田 太郎")
        masked = masker.mask("名前: 山田 太郎")
        unmasked = masker.unmask(masked)
        assert "山田 太郎" in unmasked

    def test_unmask_llm_response_comment(self):
        masker = PiiMasker(applicant_name="山田 太郎")
        masker.mask("山田 太郎の履歴書")
        comment = "[NAME_001]はIT業界で10年の経験があります。"
        result = masker.unmask(comment)
        assert result == "山田 太郎はIT業界で10年の経験があります。"

    def test_unmask_no_placeholders(self):
        masker = PiiMasker(applicant_name="山田 太郎")
        result = masker.unmask("プレースホルダーなしのテキスト")
        assert result == "プレースホルダーなしのテキスト"

    def test_unmask_empty_string(self):
        masker = PiiMasker(applicant_name="山田 太郎")
        assert masker.unmask("") == ""

    def test_unmask_none(self):
        masker = PiiMasker(applicant_name="山田 太郎")
        assert masker.unmask(None) is None


# ================================================================
#  ラウンドトリップ（マスク→アンマスク）
# ================================================================

class TestRoundTrip:
    def test_full_pipeline(self):
        resume = """氏名: 玉井 晴香
電話番号: 090-1234-5678
住所: 東京都世田谷区成城1丁目2番3号

職務経歴:
2015年 - 2020年 株式会社テスト IT部門
"""
        masker = PiiMasker(applicant_name="玉井 晴香")
        masked = masker.mask(resume)

        # PIIがマスクされている
        assert "玉井 晴香" not in masked
        assert "090-1234-5678" not in masked
        assert "1丁目2番3号" not in masked

        # 非PIIは保持
        assert "東京都世田谷区成城" in masked
        assert "株式会社テスト IT部門" in masked

        # アンマスクで復元
        unmasked = masker.unmask(masked)
        assert "玉井 晴香" in unmasked
        assert "090-1234-5678" in unmasked

    def test_masked_count(self):
        masker = PiiMasker(applicant_name="山田 太郎")
        masker.mask("山田 太郎\n電話: 090-1234-5678")
        # 名前のバリエーション + 電話番号
        assert masker.masked_count >= 2
