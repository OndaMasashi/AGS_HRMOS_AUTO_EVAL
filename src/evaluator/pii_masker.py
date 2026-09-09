"""PIIマスキング - LLM送信前に個人情報をプレースホルダーに置換"""

import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 日本語で使われる各種ハイフン・ダッシュ文字
_DASH_CHARS = r'\-\u2010\u2011\u2012\u2013\u2014\u2015\u2212\uFF0D'
_DASH_CLASS = f'[{_DASH_CHARS}]'

# 姓・名が単独で出てきたときに、企業名・学校名の一部を誤ってマスクしないための手がかり。
# 「所属企業名は評価に必要なのでマスクしない」方針を守るため、これらが近くにある箇所は残す。
_CORP_HINT = re.compile(
    r'株式会社|㈱|\(株\)|（株）|有限会社|合同会社|工業|商事|製作所|システム|テクノ|'
    r'エンジニアリング|ホールディングス|グループ|銀行|大学|学院|学園|高校|病院|クリニック'
)

_EMAIL_PATTERN = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')

# 〒なしの「123-4567」は電話番号の一部（090-1111-2222 の前半）と紛らわしいため、
# 前後にダッシュ付きの数字が続くものは除外する。電話番号のマスキングも先に済ませておく。
_POSTAL_PATTERN = re.compile(
    rf'〒\s*\d{{3}}{_DASH_CLASS}?\d{{4}}'
    rf'|(?<![\d{_DASH_CHARS}])\d{{3}}{_DASH_CLASS}\d{{4}}(?!{_DASH_CLASS}?\d)'
)

# 生年月日は「年」を残して月日だけを伏せる。年齢の判定に生年が要るため
# （年ごと消すと applicant_age が取れず、点数と無関係な「？」判定が増える）。
# 職歴の年月（2020年4月入社など）を巻き込まないよう、ラベルが近くにあるものだけを対象にする。
_BIRTH_DATE_PATTERN = re.compile(
    r'(生年月日|生 年 月 日|誕生日|Date of Birth)(.{0,15}?(?:19|20)\d{2}\s*[年/.\-]\s*)'
    r'(\d{1,2}\s*[月/.\-]\s*\d{1,2}\s*日?)',
    re.DOTALL,
)


@dataclass
class PiiMasker:
    """応募者ごとのPIIマスキング/アンマスキングを管理する。

    使用例:
        masker = PiiMasker(applicant_name="山田 太郎")
        masked_text = masker.mask(resume_text)
        # ... LLM呼び出し ...
        unmasked_comment = masker.unmask(llm_comment)
    """
    applicant_name: str
    _mapping: dict[str, str] = field(default_factory=dict, init=False)
    _reverse_mapping: dict[str, str] = field(default_factory=dict, init=False)
    _counters: dict[str, int] = field(
        default_factory=lambda: {
            "NAME": 0, "PHONE": 0, "ADDR": 0, "EMAIL": 0, "POST": 0, "DOB": 0,
        },
        init=False,
    )

    def mask(self, text: str) -> str:
        """テキスト内のPIIをプレースホルダーに置換する"""
        if not text:
            return text
        result = text
        result = self._mask_names(result)
        result = self._mask_emails(result)
        # 電話番号を先に処理する。「090-1111-2222」の前半は郵便番号と同じ形なので、
        # 郵便番号を先に消すと電話番号が半分だけ残る
        result = self._mask_phones(result)
        # 郵便番号は住所のパターンに巻き込まれる前に処理する
        result = self._mask_postal_codes(result)
        result = self._mask_birth_dates(result)
        result = self._mask_addresses(result)

        if self._mapping:
            logger.info(f"  PIIマスキング: {len(self._mapping)} 件の個人情報を置換")
        return result

    def unmask(self, text: str) -> str:
        """プレースホルダーを元のPIIに復元する"""
        if not text or not self._reverse_mapping:
            return text
        result = text
        for placeholder, original in self._reverse_mapping.items():
            result = result.replace(placeholder, original)
        return result

    def _add_mapping(self, category: str, original: str) -> str:
        """マッピングを追加し、プレースホルダーキーを返す"""
        if original in self._mapping:
            return self._mapping[original]

        self._counters[category] += 1
        key = f"[{category}_{self._counters[category]:03d}]"
        self._mapping[original] = key
        self._reverse_mapping[key] = original
        return key

    # ------------------------------------------------------------------ #
    #  氏名マスキング
    # ------------------------------------------------------------------ #
    def _mask_names(self, text: str) -> str:
        """氏名をマスキングする"""
        if not self.applicant_name:
            return text

        result = text
        name = self.applicant_name.strip()
        variants = self._generate_name_variants(name)

        # 長い文字列から順にマッチ（部分マッチの問題を回避）
        for variant in sorted(variants, key=len, reverse=True):
            if variant in result:
                placeholder = self._add_mapping("NAME", variant)
                result = result.replace(variant, placeholder)

        # フルネームだけを消しても、書類のあちこちに姓だけ・名だけが単独で残る
        # （実データ20人の検証で6人が該当した）。ここまで消して初めてマスクが成立する。
        return self._mask_name_parts(result, name)

    def _mask_name_parts(self, text: str, name: str) -> str:
        """姓・名が単独で出てくる箇所をマスキングする

        企業名・学校名の一部（例: 「田中工業」の「田中」）は評価に必要なので残す。
        1文字の姓・名は一般的な語との衝突が多すぎるため対象にしない。
        """
        result = text
        for part in [p for p in re.split(r'[\s　]+', name) if len(p) >= 2]:
            for match in reversed(list(re.finditer(re.escape(part), result))):
                start, end = match.start(), match.end()
                if _CORP_HINT.search(result[max(0, start - 6):end + 6]):
                    continue
                placeholder = self._add_mapping("NAME", part)
                result = result[:start] + placeholder + result[end:]
        return result

    # ------------------------------------------------------------------ #
    #  メールアドレス・郵便番号・生年月日のマスキング
    # ------------------------------------------------------------------ #
    def _mask_emails(self, text: str) -> str:
        """メールアドレスをマスキングする（評価には使わない情報）"""
        return self._mask_by_pattern(text, _EMAIL_PATTERN, "EMAIL")

    def _mask_postal_codes(self, text: str) -> str:
        """郵便番号をマスキングする（評価には使わない情報）"""
        return self._mask_by_pattern(text, _POSTAL_PATTERN, "POST")

    def _mask_birth_dates(self, text: str) -> str:
        """生年月日の月日をマスキングする（年は年齢判定に必要なため残す）"""
        result = text
        for match in reversed(list(_BIRTH_DATE_PATTERN.finditer(result))):
            month_day = match.group(3)
            placeholder = self._add_mapping("DOB", month_day)
            result = result[:match.start(3)] + placeholder + result[match.end(3):]
        return result

    def _mask_by_pattern(self, text: str, pattern: re.Pattern, category: str) -> str:
        """パターンに一致した箇所をまとめてマスキングする"""
        result = text
        for match in reversed(list(pattern.finditer(result))):
            placeholder = self._add_mapping(category, match.group())
            result = result[:match.start()] + placeholder + result[match.end():]
        return result

    @staticmethod
    def _generate_name_variants(name: str) -> list[str]:
        """氏名の表記ゆれバリエーションを生成する

        "山田 太郎" → ["山田 太郎", "山田　太郎", "山田太郎"]
        """
        variants = set()
        variants.add(name)

        parts = re.split(r'[\s\u3000]+', name)
        if len(parts) >= 2:
            variants.add(' '.join(parts))       # 半角スペース
            variants.add('\u3000'.join(parts))   # 全角スペース
            variants.add(''.join(parts))         # スペースなし

        return list(variants)

    # ------------------------------------------------------------------ #
    #  電話番号マスキング
    # ------------------------------------------------------------------ #
    def _mask_phones(self, text: str) -> str:
        """電話番号をマスキングする"""
        phone_patterns = [
            # ハイフン区切り: 0X-XXXX-XXXX, 0XX-XXX-XXXX 等
            rf'0\d{{1,4}}{_DASH_CLASS}\d{{1,4}}{_DASH_CLASS}\d{{3,4}}',
            # 括弧付き: (0X) XXXX-XXXX
            rf'\(0\d{{1,4}}\)\s*\d{{1,4}}{_DASH_CLASS}?\d{{3,4}}',
            # ハイフンなし 10-11桁
            r'(?<!\d)0\d{9,10}(?!\d)',
        ]

        result = text
        for pattern in phone_patterns:
            matches = list(re.finditer(pattern, result))
            for match in reversed(matches):
                phone = match.group()
                placeholder = self._add_mapping("PHONE", phone)
                result = result[:match.start()] + placeholder + result[match.end():]
        return result

    # ------------------------------------------------------------------ #
    #  住所（番地以降）マスキング
    # ------------------------------------------------------------------ #
    def _mask_addresses(self, text: str) -> str:
        """住所の番地以降をマスキングする

        都道府県・市区町村・町域名はそのまま。
        数字+丁目/番地/号 の部分以降をマスキング。
        """
        _NUM = r'[0-9０-９一二三四五六七八九十百]+'
        _NUM_OPT = rf'(?:{_NUM})?'  # 数字グループ（省略可）

        address_patterns = [
            # 丁目+番地+号: 1丁目2番3号 (以降の建物名等も含む)
            rf'{_NUM}丁目{_NUM_OPT}{_DASH_CLASS}?{_NUM_OPT}番[地]?{_DASH_CLASS}?{_NUM_OPT}号?[^\n]*',
            # 番地+号: 123番地の4
            rf'{_NUM}番地[のノ]?{_NUM_OPT}号?[^\n]*',
            # 番+号（地なし）: 2番3号
            rf'{_NUM}番{_NUM_OPT}号[^\n]*',
        ]

        result = text
        for pattern in address_patterns:
            matches = list(re.finditer(pattern, result))
            for match in reversed(matches):
                addr_detail = match.group().rstrip()
                if len(addr_detail) >= 3:
                    placeholder = self._add_mapping("ADDR", addr_detail)
                    result = result[:match.start()] + placeholder + result[match.end():]
        return result

    @property
    def masked_count(self) -> int:
        """マスキングされたPII項目数"""
        return len(self._mapping)

    @property
    def mapping_summary(self) -> dict[str, int]:
        """カテゴリ別のマスキング件数"""
        return dict(self._counters)
