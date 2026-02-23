"""LLMクライアント - 設定に基づいてClaude/Gemini CLIを切り替え"""

import logging

from src.evaluator.claude_client import call_claude, ClaudeClientError
from src.evaluator.gemini_client import call_gemini, GeminiClientError

logger = logging.getLogger(__name__)


class LLMClientError(Exception):
    """LLM CLI呼び出しエラー（プロバイダー共通）"""
    pass


def call_llm(prompt: str, config: dict) -> str:
    """設定に基づいてLLM CLIを呼び出す"""
    eval_config = config.get("evaluation", {})
    provider = eval_config.get("provider", "claude")

    try:
        if provider == "gemini":
            logger.debug("LLMプロバイダー: Gemini CLI")
            return call_gemini(prompt, config)
        else:
            logger.debug("LLMプロバイダー: Claude CLI")
            return call_claude(prompt, config)
    except (ClaudeClientError, GeminiClientError) as e:
        raise LLMClientError(str(e)) from e
