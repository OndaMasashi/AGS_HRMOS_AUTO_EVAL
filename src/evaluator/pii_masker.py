"""PIIマスキング - LLM送信前に個人情報をプレースホルダーに置換"""

import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 日本語で使われる各種ハイフン・ダッシュ文字
_DASH_CHARS = r'\-\u2010\u2011\u2012\u2013\u2014\u2015\u2212\uFF0D'
_DASH_CLASS = f'[{_DASH_CHARS}]'


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
        default_factory=lambda: {"NAME": 0, "PHONE": 0, "ADDR": 0}, init=False
    )

    def mask(self, text: str) -> str:
        """テキスト内のPIIをプレースホルダーに置換する"""
        if not text:
            return text
        result = text
        result = self._mask_names(result)
        result = self._mask_phones(result)
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
