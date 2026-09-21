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

    # ハイフンで書いた番地は実データで最も多い書き方（2026-09-21 に 399 行が素通りしていた）
    def test_hyphen_banchi_with_building(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("東京都中野区本町3-5-8 サンプルハイツ202")
        assert "3-5-8" not in result
        assert "サンプルハイツ202" not in result
        assert "東京都中野区本町" in result
        assert masker.mapping_summary["ADDR"] == 1

    def test_chome_with_hyphen(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("神奈川県横浜市港北区日吉2丁目4-6")
        assert "2丁目4-6" not in result
        assert "神奈川県横浜市港北区日吉" in result

    def test_fullwidth_hyphen_banchi(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("埼玉県さいたま市浦和区高砂１－２－３")
        assert "１－２－３" not in result
        assert "埼玉県さいたま市浦和区高砂" in result

    def test_long_vowel_as_hyphen_from_pdf(self):
        # PDF から取り出すとハイフンが長音符に化けることがある
        masker = PiiMasker(applicant_name="")
        result = masker.mask("静岡県静岡市葵区見本町9ー6ー1")
        assert "9ー6ー1" not in result
        assert "静岡県静岡市葵区見本町" in result

    def test_two_part_hyphen_banchi(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("千葉県千葉市中央区富士見12-3")
        assert "12-3" not in result

    def test_career_years_after_prefecture_are_kept(self):
        # 職歴の年は在籍期間の評価に要るので消さない
        masker = PiiMasker(applicant_name="")
        text = "東京都港区 2019-2021 受託開発企業にて勤務"
        assert masker.mask(text) == text

    def test_career_line_without_banchi_is_kept(self):
        masker = PiiMasker(applicant_name="")
        text = "2019年4月～2021年3月 東京都港区の受託開発企業に勤務"
        assert masker.mask(text) == text

    def test_stops_before_other_placeholder(self):
        # 同じ行の電話番号の置換結果を住所の中に取り込まず、元に戻せること
        masker = PiiMasker(applicant_name="")
        text = "東京都中野区本町3-5-8 090-1234-5678"
        result = masker.mask(text)
        assert "[PHONE_001]" in result
        assert "[ADDR_001]" in result
        assert masker.unmask(result) == text

    # 番地から行末までを消すと、PDF で同じ行に並んだ職歴・学歴まで消える
    # （点数が下がると取り消せない自動NG登録につながる）
    def test_career_on_same_line_is_kept(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("大阪府大阪市北区梅田2-4-9 A社 2018-2020 営業")
        assert "2-4-9" not in result
        assert "A社 2018-2020 営業" in result

    def test_education_on_same_line_is_kept(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("住所 東京都港区芝浦1-2-3 学歴 2015年3月 サンプル大学卒業")
        assert "1-2-3" not in result
        assert "学歴 2015年3月 サンプル大学卒業" in result

    def test_career_after_banchi_go_is_kept(self):
        # 既存の「番」「号」の書き方も同じく建物名までで止める
        masker = PiiMasker(applicant_name="")
        result = masker.mask("東京都港区芝5丁目7番1号 A社 2018-2020")
        assert "5丁目7番1号" not in result
        assert "A社 2018-2020" in result

    def test_building_and_room_after_space_are_masked(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("東京都中野区本町3-5-8 メゾンサンプル 405")
        assert "メゾンサンプル" not in result
        assert "405" not in result

    def test_career_sentence_without_space_is_kept(self):
        # 日本語の文は空白で区切られないので、番地に直接続く職歴も守る
        masker = PiiMasker(applicant_name="")
        result = masker.mask("東京都港区芝5-7-1、株式会社サンプルにてPM")
        assert "5-7-1" not in result
        assert "、株式会社サンプルにてPM" in result

    def test_particle_after_banchi_is_kept(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("東京都港区芝5-7-1の本社にて勤務")
        assert "の本社にて勤務" in result

    def test_building_without_keyword_but_room_number_is_masked(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("東京都杉並区本町1-2-3 コスモ見本101")
        assert "コスモ見本101" not in result

    def test_company_name_with_number_is_kept(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("東京都港区芝1-2-3 サンプルシステム2 勤務")
        assert "サンプルシステム2 勤務" in result

    def test_company_attached_to_banchi_is_kept(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("東京都港区芝浦3-4-1株式会社サンプル 営業部")
        assert "3-4-1" not in result
        assert "株式会社サンプル 営業部" in result

    def test_company_attached_to_banchi_go_is_kept(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("大阪府大阪市北区梅田1丁目2番3号株式会社サンプル営業部長")
        assert "1丁目2番3号" not in result
        assert "株式会社サンプル営業部長" in result

    def test_company_building_is_kept(self):
        # 建物の目印（ビル）を含んでいても、会社名なら職歴として残す
        masker = PiiMasker(applicant_name="")
        result = masker.mask("東京都大田区蒲田5-13-26 株式会社ABC本社ビル")
        assert "5-13-26" not in result
        assert "株式会社ABC本社ビル" in result

    def test_building_starting_with_ka_is_masked(self):
        # 「ヶ月」「カ月」の判定が、カで始まる建物名を巻き込まないこと
        masker = PiiMasker(applicant_name="")
        result = masker.mask("東京都中野区本町3-5-8カーサ見本101")
        assert "3-5-8" not in result
        assert "カーサ見本101" not in result

    def test_number_ranges_in_career_are_kept(self):
        masker = PiiMasker(applicant_name="")
        for text in [
            "東京都港区の企業で2-3年勤務",
            "東京都港区の企業で3-4名をマネジメント",
            "東京都港区 15-18期 在籍",
            "東京都港区の企業で6-8ヶ月の案件を担当",
        ]:
            assert masker.mask(text) == text, text

    def test_kanji_ichiban_in_career_is_kept(self):
        masker = PiiMasker(applicant_name="")
        text = "東京都渋谷区のWeb制作会社で一番の売上を達成"
        assert masker.mask(text) == text

    def test_japanese_era_years_are_kept(self):
        masker = PiiMasker(applicant_name="")
        text = "東京都港区 H31-R3 勤務"
        assert masker.mask(text) == text

    def test_kanji_town_name_is_kept(self):
        # 「六番町」は町名。番地の 6-2 だけを消す
        masker = PiiMasker(applicant_name="")
        result = masker.mask("東京都千代田区六番町6-2")
        assert "東京都千代田区六番町" in result
        assert "6-2" not in result


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


# ==================================================================== #
#  メールアドレス・郵便番号・生年月日のマスキング
# ==================================================================== #
class TestEmailMasking:
    def test_mask_email(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("連絡先: taro.yamada@example.co.jp")
        assert "taro.yamada@example.co.jp" not in result
        assert "[EMAIL_001]" in result

    def test_unmask_email(self):
        masker = PiiMasker(applicant_name="")
        masked = masker.mask("mail: a.b+c@example.com")
        assert masker.unmask(masked) == "mail: a.b+c@example.com"


class TestPostalCodeMasking:
    def test_with_mark(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("〒123-4567 東京都世田谷区成城")
        assert "123-4567" not in result
        # 都道府県・市区町村は評価に使うため残す
        assert "東京都世田谷区成城" in result

    def test_without_mark(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("住所 123-4567 東京都")
        assert "123-4567" not in result

    def test_phone_not_treated_as_postal(self):
        """携帯番号の前半（090-1111）を郵便番号と誤判定しない"""
        masker = PiiMasker(applicant_name="")
        result = masker.mask("携帯: 090-1111-2222")
        assert "090-1111-2222" not in result
        assert "[PHONE_001]" in result
        assert "POST" not in result


class TestBirthDateMasking:
    def test_mask_month_day_keep_year(self):
        """月日は伏せるが、年齢の判定に要る「年」は残す"""
        masker = PiiMasker(applicant_name="")
        result = masker.mask("生年月日: 1990年5月3日")
        assert "5月3日" not in result
        assert "1990年" in result

    def test_label_on_separate_line(self):
        masker = PiiMasker(applicant_name="")
        result = masker.mask("生年月日\n1985年12月24日")
        assert "12月24日" not in result
        assert "1985年" in result

    def test_work_history_not_masked(self):
        """職歴の年月日は在籍期間の評価に必要なのでマスクしない"""
        masker = PiiMasker(applicant_name="")
        text = "2020年4月1日 株式会社テストに入社\n2023年3月31日 退社"
        assert masker.mask(text) == text


class TestNamePartMasking:
    def test_surname_alone(self):
        """書類のあちこちに姓だけが残らないこと"""
        masker = PiiMasker(applicant_name="山田 太郎")
        result = masker.mask("氏名: 山田 太郎\n面談メモ: 山田は前職で")
        assert "山田" not in result

    def test_given_name_alone(self):
        masker = PiiMasker(applicant_name="佐々木 健太")
        result = masker.mask("佐々木 健太\n健太さんの担当案件")
        assert "健太" not in result

    def test_corporate_name_preserved(self):
        """企業名の一部と一致する姓は評価に必要なので残す"""
        masker = PiiMasker(applicant_name="田中 一郎")
        result = masker.mask("株式会社田中工業に在籍")
        assert "田中工業" in result

    def test_single_char_part_not_masked(self):
        """1文字の姓・名は一般的な語と衝突するため対象にしない"""
        masker = PiiMasker(applicant_name="林 大")
        result = masker.mask("大変多くの経験を積んだ")
        assert "大変多くの経験を積んだ" in result
