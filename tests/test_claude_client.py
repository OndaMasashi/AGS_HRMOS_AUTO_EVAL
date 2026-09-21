"""Claude CLI の起動方法のユニットテスト

評価役の AI は、プロジェクトの外で・会話を保存せず・道具を持たせずに動かす。
これが崩れると開発用の CLAUDE.md が採点の文脈に混ざり（2026-09-16/17 に
それを理由とした評価拒否が実際に発生）、書類本文が会話記録として残り続ける。
実際の CLI は呼ばず、起動引数と起動フォルダだけを確かめる。
"""

from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from src.evaluator import claude_client

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG = {"evaluation": {"model": "opus", "max_retries": 1}}


def _captured_call():
    """call_claude が subprocess.run に渡した引数を返す"""
    done = CompletedProcess([], 0, stdout="{}", stderr="")
    with patch.object(claude_client.subprocess, "run", return_value=done) as run:
        claude_client.call_claude("prompt", CONFIG)
    return run.call_args


class TestClaudeInvocation:
    def test_passes_model(self):
        cmd = _captured_call().args[0]
        assert cmd[cmd.index("--model") + 1] == "opus"

    def test_does_not_persist_session(self):
        assert "--no-session-persistence" in _captured_call().args[0]

    def test_disables_all_tools_as_last_argument(self):
        # --tools は値を複数取るため、最後に空文字1つで終わっていないと
        # 後ろの引数を道具名として吸い込む
        assert _captured_call().args[0][-2:] == ["--tools", ""]

    def test_runs_outside_project(self):
        cwd = Path(_captured_call().kwargs["cwd"]).resolve()
        assert cwd.is_dir()
        assert cwd != PROJECT_ROOT and PROJECT_ROOT not in cwd.parents

    def test_no_claude_md_up_the_tree(self):
        # Claude CLI は起動フォルダから親をさかのぼって CLAUDE.md を読む
        cwd = Path(_captured_call().kwargs["cwd"]).resolve()
        assert not any((d / "CLAUDE.md").exists() for d in [cwd, *cwd.parents])
