"""Gemini APIクライアント - REST API を直接呼び出す（CLI・Node.js 不要）

Gemini CLI は 2026-06-18 に個人アカウント（無料枠 / Google AI Pro / Ultra）向けの
リクエスト提供を終了したため、APIキー認証で REST API を直接叩く経路を用意する。
CLI を挟まないため Node.js もブラウザでの対話ログインも不要になり、
タスクスケジューラからの無人実行との相性が良い。
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 5
DEFAULT_TIMEOUT = 300
# 同単価の gemini-2.5-flash より実測で約5倍速く、既存評価との一致度も高い
DEFAULT_MODEL = "gemini-3.5-flash-lite"

API_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

# リトライしても回復しないため即座に中断するHTTPステータス
FATAL_STATUS_CODES = (400, 401, 403, 404)


class GeminiApiClientError(Exception):
    """Gemini API呼び出しエラー"""
    pass


def _resolve_api_key(eval_config: dict) -> str:
    """APIキーを環境変数優先で解決する"""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        api_key = str(eval_config.get("gemini_api_key", "")).strip()

    if not api_key:
        raise GeminiApiClientError(
            "Gemini APIキーが設定されていません。\n"
            "  環境変数 GEMINI_API_KEY を設定するか、config.yaml の "
            "evaluation.gemini_api_key に設定してください。\n"
            "  キーの取得: https://aistudio.google.com/apikey"
        )
    return api_key


def _extract_text(payload: dict) -> str:
    """API応答から本文テキストを取り出す"""
    candidates = payload.get("candidates") or []
    if not candidates:
        # 安全性フィルタ等でブロックされた場合は candidates が空になる
        reason = (payload.get("promptFeedback") or {}).get("blockReason", "不明")
        raise GeminiApiClientError(
            f"Gemini APIが応答を返しませんでした（ブロック理由: {reason}）"
        )

    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()

    if not text:
        finish_reason = candidate.get("finishReason", "不明")
        raise GeminiApiClientError(
            f"Gemini APIが空の応答を返しました（finishReason: {finish_reason}）"
        )
    return text


def call_gemini_api(prompt: str, config: dict) -> str:
    """Gemini REST APIを呼び出し、応答本文を返す"""
    eval_config = config.get("evaluation", {})
    max_retries = eval_config.get("max_retries", DEFAULT_MAX_RETRIES)
    retry_delay = eval_config.get("retry_delay", DEFAULT_RETRY_DELAY)
    timeout = eval_config.get("timeout", DEFAULT_TIMEOUT)
    model = eval_config.get("model", DEFAULT_MODEL)

    api_key = _resolve_api_key(eval_config)

    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            # 評価のブレを抑え、JSON以外の前置きが混ざらないようにする
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }
    ).encode("utf-8")

    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.debug(f"Gemini API呼び出し (試行 {attempt}/{max_retries}, model={model})")

            request = urllib.request.Request(
                API_ENDPOINT.format(model=model),
                data=body,
                headers={
                    "Content-Type": "application/json",
                    # キーをURLに載せるとログに残るためヘッダで渡す
                    "x-goog-api-key": api_key,
                },
                method="POST",
            )

            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))

            text = _extract_text(payload)

            usage = payload.get("usageMetadata", {})
            logger.debug(
                f"  トークン: 入力 {usage.get('promptTokenCount')} / "
                f"出力 {usage.get('candidatesTokenCount')}"
            )
            return text

        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:300]
            if e.code in FATAL_STATUS_CODES:
                raise GeminiApiClientError(
                    f"Gemini API エラー (HTTP {e.code}): {detail}\n"
                    "  APIキーの有効性・課金設定・モデル名を確認してください。"
                ) from e
            # 429（レート超過）・5xx（一時障害）はリトライで回復しうる
            last_error = GeminiApiClientError(f"Gemini API エラー (HTTP {e.code}): {detail}")
            logger.warning(f"  HTTP {e.code} (試行 {attempt}/{max_retries})")
        except urllib.error.URLError as e:
            last_error = GeminiApiClientError(f"Gemini API 通信エラー: {e.reason}")
            logger.warning(f"  通信エラー (試行 {attempt}/{max_retries}): {e.reason}")
        except TimeoutError:
            last_error = GeminiApiClientError(f"Gemini API タイムアウト ({timeout}秒)")
            logger.warning(f"  タイムアウト (試行 {attempt}/{max_retries})")
        except (json.JSONDecodeError, KeyError) as e:
            last_error = GeminiApiClientError(f"Gemini API 応答の解釈に失敗: {e}")
            logger.warning(f"  応答解釈エラー (試行 {attempt}/{max_retries}): {e}")
        except GeminiApiClientError as e:
            last_error = e
            logger.warning(f"  エラー (試行 {attempt}/{max_retries}): {e}")

        if attempt < max_retries:
            logger.info(f"  {retry_delay}秒後にリトライ...")
            time.sleep(retry_delay)

    raise last_error or GeminiApiClientError("Gemini API呼び出しに失敗しました")
