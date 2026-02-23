"""Gemini CLIクライアント - subprocess経由でGemini AIを呼び出す"""

import logging
import subprocess
import sys
import time

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 5
DEFAULT_TIMEOUT = 120


class GeminiClientError(Exception):
    """Gemini CLI呼び出しエラー"""
    pass


def call_gemini(prompt: str, config: dict) -> str:
    """Gemini CLIをsubprocess経由で呼び出し、stdoutを返す"""
    eval_config = config.get("evaluation", {})
    max_retries = eval_config.get("max_retries", DEFAULT_MAX_RETRIES)
    retry_delay = eval_config.get("retry_delay", DEFAULT_RETRY_DELAY)
    timeout = eval_config.get("timeout", DEFAULT_TIMEOUT)
    use_shell = eval_config.get("shell", False)

    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.debug(f"Gemini CLI呼び出し (試行 {attempt}/{max_retries})")

            # Windows: npmグローバルインストールは.cmdラッパー経由
            cmd = ["gemini.cmd"] if sys.platform == "win32" else ["gemini"]

            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                shell=use_shell,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() or f"Exit code: {result.returncode}"
                raise GeminiClientError(f"Gemini CLI エラー: {error_msg}")

            output = result.stdout.strip()
            if not output:
                raise GeminiClientError("Gemini CLIが空の応答を返しました")

            return output

        except subprocess.TimeoutExpired:
            last_error = GeminiClientError(f"Gemini CLI タイムアウト ({timeout}秒)")
            logger.warning(f"  タイムアウト (試行 {attempt}/{max_retries})")
        except FileNotFoundError:
            raise GeminiClientError(
                "gemini コマンドが見つかりません。Gemini CLIがインストールされているか確認してください。\n"
                "  インストール: npm install -g @google/gemini-cli"
            )
        except GeminiClientError as e:
            last_error = e
            logger.warning(f"  エラー (試行 {attempt}/{max_retries}): {e}")

        if attempt < max_retries:
            logger.info(f"  {retry_delay}秒後にリトライ...")
            time.sleep(retry_delay)

    raise last_error or GeminiClientError("Gemini CLI呼び出しに失敗しました")
