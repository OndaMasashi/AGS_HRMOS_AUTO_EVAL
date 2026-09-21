"""Claude CLIクライアント - subprocess経由でClaude AIを呼び出す"""

import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 5
DEFAULT_TIMEOUT = 120
MAX_TEXT_CHARS = 80000
# config.yaml の evaluation.model が未設定のときに使うモデル。
# エイリアス（sonnet / opus）で書くと、その時点の各世代の既定モデルに解決される。
DEFAULT_MODEL = "sonnet"

# claude -p を起動する作業フォルダ。プロジェクトの外（%TEMP%）に置く。
# Claude CLI は起動フォルダとその親をさかのぼって CLAUDE.md を読み込むため、
# プロジェクト配下で起動すると開発用の CLAUDE.md（自動NG登録や年齢の閾値の説明）が
# 評価の文脈に混ざり、採点がそれに左右されるうえ、それを理由に評価を拒否される
# （2026-09-16/17 に実際に発生）。呼び出しごとに別名にすると ~/.claude/projects/ に
# フォルダが増えていくため、固定の名前で使い回す。
# ~/.claude/CLAUDE.md（ユーザー全体の設定）はフォルダを変えても外れない可能性がある
# （2026-09-21 の確認では AI は「文脈に無い」と答えたが、自己申告なので確証ではない）。
# 確実に外せる --bare は APIキー認証が必須で、対話ログインで動かす本ツールでは使えない。
ISOLATED_WORKDIR_NAME = "hrmos_auto_eval_llm"


def _isolated_workdir() -> Path:
    """claude -p を起動する、プロジェクト外の作業フォルダを返す"""
    workdir = Path(tempfile.gettempdir()) / ISOLATED_WORKDIR_NAME
    workdir.mkdir(exist_ok=True)
    return workdir


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

    # モデルは必ず明示する。無指定だと Claude CLI の既定モデル（= 開発者が
    # Claude Code で選んでいるモデル）が使われ、評価者の意図と無関係に採点基準が
    # 変わってしまう。実際、2026-09-09 に既定モデルが CLI の対応外バージョンへ
    # 変わり、claude -p が API Error 400 で全件失敗する状態になった。
    model = eval_config.get("model") or DEFAULT_MODEL
    # --no-session-persistence: 書類本文を含む会話が ~/.claude/projects/ に保存され
    #   続けるのを止める（評価結果の全文は DB の raw_response に残る）。
    # --tools "": 評価役にファイル読み取り等の道具を持たせない。書類本文は外部から
    #   来た文章なので、そこに書かれた指示で config.yaml 等を読まれないようにする。
    #   値を複数取れるオプションなので、後ろの引数を吸い込まないよう必ず最後に置く
    #   （プロンプトは標準入力で渡すため位置引数は無い）。
    #   作業フォルダに置いたファイルを読めないことは実機で確認済み（2026-09-21）。
    # --safe-mode は付けない。MCP 等も止まる触れ込みだが、実機では併用すると
    #   道具を使ったかのような架空の結果を AI が作文した（ファイルは読めていない）。
    #   採点の根拠に作り話が混ざるおそれがある。
    cmd = [
        "claude", "-p", "--model", model,
        "--no-session-persistence", "--tools", "",
    ]
    workdir = _isolated_workdir()

    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.debug(f"Claude CLI呼び出し (試行 {attempt}/{max_retries})")

            # CLAUDECODE環境変数を除外（ネストセッション検出を回避）
            env = os.environ.copy()
            env.pop("CLAUDECODE", None)

            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                shell=use_shell,
                env=env,
                cwd=workdir,
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
