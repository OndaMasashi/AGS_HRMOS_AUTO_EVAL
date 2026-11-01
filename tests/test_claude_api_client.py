"""Claude API クライアントのユニットテスト

実際の API は呼ばず、SDK のクライアントを偽物に差し替えて次を確かめる。
- 本文より先に終わり方を見る（拒否・途中切れを評価として取り込まない）
- 再試行するエラーとしないエラーの区別（残高不足で無駄に再試行しない）
- API キーの置き場の検査と、エラー文での伏せ字（ログとメールに出るため）
- 送り先・モデル・effort・自動リトライ無効を SDK に渡していること
"""

from types import SimpleNamespace
from unittest.mock import patch

import anthropic
import httpx2
import pytest

from src.config import validate_config
from src.evaluator import claude_api_client
from src.evaluator.claude_api_client import ClaudeApiClientError, call_claude_api

CONFIG = {
    "evaluation": {
        "provider": "claude_api",
        "model": "claude-opus-5-5",
        "max_retries": 3,
        "retry_delay": 0,
    }
}


def _message(text='{"ok": true}', stop_reason="end_turn", category=None):
    """SDK の Message に似せた応答（思考ブロック＋本文）"""
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(category=category) if category else None,
        model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=100, output_tokens=200),
    )


def _status_error(cls, status, message="error message", kind="api_error"):
    """SDK が投げるのと同じ形の HTTP エラー"""
    body = {"type": "error", "error": {"type": kind, "message": message}}
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(status, request=request, json=body)
    return cls(message, response=response, body=body)


class _FakeStream:
    def __init__(self, message):
        self._message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._message


class _FakeClient:
    """outcomes を順に返す（例外なら投げる）偽のクライアント"""

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = []
        # 本物と同じ client.messages.stream(...) の形で呼べるようにする
        self.messages = self

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return _FakeStream(outcome)


def _call(outcomes):
    """偽のクライアントで call_claude_api を呼び、(結果または例外, クライアント) を返す"""
    client = _FakeClient(outcomes)
    with patch.object(claude_api_client, "read_api_key", return_value="sk-ant-test"), \
            patch.object(claude_api_client, "_create_client", return_value=client), \
            patch.object(claude_api_client.time, "sleep"):
        try:
            return call_claude_api("prompt", CONFIG), client
        except ClaudeApiClientError as e:
            return e, client


class TestResponseHandling:
    def test_returns_text_without_thinking(self):
        result, _ = _call([_message('{"ok": true}')])
        assert result == '{"ok": true}'

    def test_refusal_fails_with_category_and_no_retry(self):
        result, client = _call([_message("", stop_reason="refusal", category="general_harms")])
        assert isinstance(result, ClaudeApiClientError)
        assert "general_harms" in str(result)
        assert len(client.calls) == 1

    def test_truncated_response_is_not_used(self):
        # 上限で切れた JSON の断片を評価として取り込まない
        result, client = _call([_message('{"evaluations": [', stop_reason="max_tokens")])
        assert isinstance(result, ClaudeApiClientError)
        assert "max_tokens" in str(result)
        assert len(client.calls) == 1

    def test_empty_text_is_retried(self):
        result, client = _call([_message(""), _message('{"ok": true}')])
        assert result == '{"ok": true}'
        assert len(client.calls) == 2

    def test_refusal_text_is_logged(self, caplog):
        # 会話は保存されないので、断られた理由を後から読めるよう本文をログに残す
        with caplog.at_level("WARNING"):
            _call([_message("この依頼には応じられません", stop_reason="refusal")])
        assert "この依頼には応じられません" in caplog.text


class TestErrorHandling:
    def test_rate_limit_is_retried(self):
        result, client = _call([
            _status_error(anthropic.RateLimitError, 429, kind="rate_limit_error"),
            _message('{"ok": true}'),
        ])
        assert result == '{"ok": true}'
        assert len(client.calls) == 2

    def test_overloaded_is_retried(self):
        result, client = _call([
            _status_error(anthropic.OverloadedError, 529, kind="overloaded_error"),
            _message('{"ok": true}'),
        ])
        assert result == '{"ok": true}'
        assert len(client.calls) == 2

    def test_low_credit_is_not_retried_and_keeps_api_message(self):
        # 残高不足は再試行しても回復しない。Console で何をすべきかが分かるよう文言は言い換えない
        api_message = "Your credit balance is too low to access the Anthropic API."
        result, client = _call([
            _status_error(anthropic.BadRequestError, 400, api_message, "invalid_request_error"),
        ])
        assert isinstance(result, ClaudeApiClientError)
        assert api_message in str(result)
        assert "HTTP 400" in str(result)
        assert len(client.calls) == 1

    def test_overload_in_the_middle_of_stream_is_retried(self):
        # 受信中に届く error イベントは、SDK が HTTP 200 のまま例外にする
        result, client = _call([
            _status_error(anthropic.APIStatusError, 200, "Overloaded", "overloaded_error"),
            _message('{"ok": true}'),
        ])
        assert result == '{"ok": true}'
        assert len(client.calls) == 2

    def test_unknown_error_type_in_the_middle_of_stream_is_not_retried(self):
        result, client = _call([
            _status_error(anthropic.APIStatusError, 200, "bad", "invalid_request_error"),
        ])
        assert isinstance(result, ClaudeApiClientError)
        assert "応答の途中" in str(result)
        assert len(client.calls) == 1

    def test_transport_error_while_reading_is_retried_and_redacted(self):
        # 受信途中の切断は通信ライブラリの例外のまま出てくる。キーを伏せたうえで再試行する
        result, client = _call([
            httpx2.RemoteProtocolError("peer closed connection sk-ant-SECRETVALUE"),
            _message('{"ok": true}'),
        ])
        assert result == '{"ok": true}'
        assert len(client.calls) == 2

        result, _ = _call([httpx2.ReadTimeout("read timed out sk-ant-SECRETVALUE")] * 3)
        assert isinstance(result, ClaudeApiClientError)
        assert "SECRETVALUE" not in str(result)

    def test_gives_up_after_max_retries(self):
        result, client = _call([_status_error(anthropic.InternalServerError, 500)] * 3)
        assert isinstance(result, ClaudeApiClientError)
        assert len(client.calls) == 3

    def test_api_key_in_error_is_redacted(self):
        # 本物と紛らわしくないよう短い偽のキー（機密スキャンの検出対象は20文字以上）
        leaked = "invalid header value sk-ant-SECRETVALUE"
        result, _ = _call([
            _status_error(anthropic.AuthenticationError, 401, leaked, "authentication_error"),
        ])
        assert "SECRETVALUE" not in str(result)
        assert "sk-ant-***" in str(result)


class TestRequest:
    def test_sends_model_and_effort(self):
        _, client = _call([_message()])
        kwargs = client.calls[0]
        assert kwargs["model"] == "claude-opus-5-5"
        assert kwargs["output_config"] == {"effort": "medium"}
        assert kwargs["messages"] == [{"role": "user", "content": "prompt"}]

    def test_client_pins_base_url_and_disables_sdk_retries(self):
        with patch.object(anthropic, "Anthropic") as ctor:
            claude_api_client._create_client("sk-ant-test", 300)
        kwargs = ctor.call_args.kwargs
        assert kwargs["base_url"] == "https://api.anthropic.com"
        assert kwargs["max_retries"] == 0
        assert kwargs["api_key"] == "sk-ant-test"


class TestApiKeyFile:
    def _read(self, tmp_path, content=None):
        key_file = tmp_path / "anthropic-api-key"
        if content is not None:
            key_file.write_text(content, encoding="utf-8")
        with patch.object(claude_api_client, "api_key_path", return_value=key_file):
            return claude_api_client.read_api_key()

    def test_reads_valid_key(self, tmp_path):
        assert self._read(tmp_path, "sk-ant-api03-abc_DEF-123\n") == "sk-ant-api03-abc_DEF-123"

    def test_missing_file_explains_how_to_save(self, tmp_path):
        with pytest.raises(ClaudeApiClientError, match="set-anthropic-key.ps1"):
            self._read(tmp_path)

    def test_rejects_admin_key(self, tmp_path):
        with pytest.raises(ClaudeApiClientError, match="Admin"):
            self._read(tmp_path, "sk-ant-admin01-abc")

    def test_rejects_malformed_key_without_echoing_it(self, tmp_path):
        with pytest.raises(ClaudeApiClientError) as excinfo:
            self._read(tmp_path, "sk-ant-api03-abc１")  # 全角文字が混ざったもの
        assert "abc" not in str(excinfo.value)


class TestConfigValidation:
    BASE = {"evaluation_criteria": [{"name": "経験", "description": "説明"}]}

    def _errors(self, evaluation):
        return validate_config({**self.BASE, "evaluation": evaluation})

    def test_claude_api_requires_full_model_name(self):
        errors = self._errors({"provider": "claude_api", "model": "opus"})
        assert any("claude-opus-5-5" in e for e in errors)

    def test_claude_api_with_full_model_name_is_valid(self):
        assert self._errors({"provider": "claude_api", "model": "claude-opus-5-5"}) == []

    def test_unknown_provider_is_rejected(self):
        errors = self._errors({"provider": "claud"})
        assert any("evaluation.provider" in e for e in errors)

    def test_doctor_reports_missing_sdk(self):
        # SDK が無いのに診断が OK だと、scan で全員が失敗するまで気づけない
        from src import doctor

        with patch("importlib.util.find_spec", return_value=None):
            status, _, detail = doctor._check_claude_api_key()
        assert status == doctor.NG
        assert "anthropic" in detail

    def test_existing_providers_stay_valid(self):
        for provider in ("gemini_api", "claude", "gemini"):
            assert self._errors({"provider": provider, "model": "opus"}) == []
