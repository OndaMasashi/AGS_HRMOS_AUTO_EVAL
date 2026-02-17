"""キーワード検索モジュール - テキスト内のキーワードマッチ検出"""

import logging
import re

logger = logging.getLogger(__name__)

# マッチ前後の文脈として抽出する文字数
CONTEXT_CHARS = 50


def scan_text(text: str, keywords: list[str]) -> list[dict]:
    """テキスト内でキーワードを検索し、マッチ結果を返す

    Returns:
        list[dict]: マッチ結果のリスト。各要素は:
            - keyword: マッチしたキーワード
            - context: マッチ箇所の前後テキスト
            - position: マッチした文字位置
    """
    if not text:
        return []

    matches = []
    seen = set()  # 同一キーワード・同一位置の重複を排除

    for keyword in keywords:
        # 大文字/小文字を区別しない、単語境界付き検索
        # 英字キーワードは \b で単語境界を付け、"mail" 等の誤検知を防止
        escaped = re.escape(keyword)
        if re.fullmatch(r'[A-Za-z0-9_]+', keyword):
            escaped = rf'\b{escaped}\b'
        pattern = re.compile(escaped, re.IGNORECASE)

        for match in pattern.finditer(text):
            pos = match.start()
            key = (keyword.lower(), pos)
            if key in seen:
                continue
            seen.add(key)

            # 前後の文脈を抽出
            context_start = max(0, pos - CONTEXT_CHARS)
            context_end = min(len(text), pos + len(keyword) + CONTEXT_CHARS)
            context = text[context_start:context_end].strip()
            # 改行を空白に置換して見やすくする
            context = re.sub(r"\s+", " ", context)

            # 文脈の前後に省略記号を付ける
            if context_start > 0:
                context = "..." + context
            if context_end < len(text):
                context = context + "..."

            matches.append({
                "keyword": keyword,
                "context": context,
                "position": pos,
            })

    if matches:
        logger.info(f"  {len(matches)} 件のキーワードマッチを検出")

    return matches
