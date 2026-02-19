"""Claude CLIクライアント - subprocess経由でClaude AIを呼び出す"""

import logging
import subprocess
import time

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 5
DEFAULT_TIMEOUT = 120
MAX_TEXT_CHARS = 80000


class ClaudeClientError(Exception):
    """Claude CLI呼び出しエラー"""
    pass


def call_claude(prompt: str, config: dict) -> str:
    """Claude CLIをsubprocess経由で呼び出し、stdoutを返す"""
    eval_config = config.get("evaluation", {})
    max_retries = eval_config.get("max_retries", DEFAULT_MAX_RETRIES)
    retry_delay = eval_config.get("retry_delay", DEFAULT_RETRY_DELAY)
    timeout = eval_config.get("timeout", DEFAULT_TIMEOUT)
    use_shell = eval_config.get("shell", False)

    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.debug(f"Claude CLI呼び出し (試行 {attempt}/{max_retries})")

            result = subprocess.run(
                ["claude", "-p"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                shell=use_shell,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() or f"Exit code: {result.returncode}"
                raise ClaudeClientError(f"Claude CLI エラー: {error_msg}")

            output = result.stdout.strip()
            if not output:
                raise ClaudeClientError("Claude CLIが空の応答を返しました")

            return output

        except subprocess.TimeoutExpired:
            last_error = ClaudeClientError(f"Claude CLI タイムアウト ({timeout}秒)")
            logger.warning(f"  タイムアウト (試行 {attempt}/{max_retries})")
        except FileNotFoundError:
            raise ClaudeClientError(
                "claude コマンドが見つかりません。Claude CLIがインストールされているか確認してください。"
            )
        except ClaudeClientError as e:
            last_error = e
            logger.warning(f"  エラー (試行 {attempt}/{max_retries}): {e}")

        if attempt < max_retries:
            logger.info(f"  {retry_delay}秒後にリトライ...")
            time.sleep(retry_delay)

    raise last_error or ClaudeClientError("Claude CLI呼び出しに失敗しました")


def truncate_text(text: str, max_chars: int = MAX_TEXT_CHARS) -> str:
    """テキストをトークン制限を考慮して切り詰める"""
    if len(text) <= max_chars:
        return text

    logger.warning(f"  テキストが長すぎるため切り詰め: {len(text)} → {max_chars} 文字")
    return text[:max_chars] + "\n\n[...テキストが長いため以降省略...]"
