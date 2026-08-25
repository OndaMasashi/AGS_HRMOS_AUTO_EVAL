"""LLMクライアント - 設定に基づいてプロバイダーを切り替え"""

import logging

from src.evaluator.claude_client import call_claude, ClaudeClientError
from src.evaluator.gemini_api_client import call_gemini_api, GeminiApiClientError
from src.evaluator.gemini_client import call_gemini, GeminiClientError

logger = logging.getLogger(__name__)


class LLMClientError(Exception):
    """LLM呼び出しエラー（プロバイダー共通）"""
    pass


def call_llm(prompt: str, config: dict) -> str:
    """設定に基づいてLLMを呼び出す"""
    eval_config = config.get("evaluation", {})
    provider = eval_config.get("provider", "claude")

    try:
        if provider == "gemini_api":
            logger.debug("LLMプロバイダー: Gemini API（APIキー認証）")
            return call_gemini_api(prompt, config)
        if provider == "gemini":
            # Gemini CLI は 2026-06-18 に個人アカウント向け提供を終了している
            logger.warning(
                "provider: \"gemini\"（CLI経由）は個人アカウントでは利用できません。"
                "APIキー認証の \"gemini_api\" への移行を推奨します。"
            )
            return call_gemini(prompt, config)
        logger.debug("LLMプロバイダー: Claude CLI")
        return call_claude(prompt, config)
    except (ClaudeClientError, GeminiClientError, GeminiApiClientError) as e:
        raise LLMClientError(str(e)) from e
