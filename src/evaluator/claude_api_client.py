"""Claude APIクライアント - 公式SDK（anthropic）で Messages API を直接呼び出す

claude -p（Claude CLI）はプランの使用枠を消費し、Claude Console に毎月付与される
プロモーションクレジット（Max / Team プラン付属）の対象外になる（Claude Code は対象外）。
このクレジットから払うため、CLI を挟まず SDK で直接呼ぶ。Console の自動チャージを
オフにしていれば、使い切っても API が止まるだけで請求は来ない（エラー文がそのまま出る）。

API は CLAUDE.md を読まないので、CLI で必要だった回避策（プロジェクト外での起動・
道具の禁止・CLAUDECODE の除去）は要らない。2026-09-16/17 に開発用の CLAUDE.md が
評価の文脈に混ざって評価を拒否された問題も、この経路では起きない。
"""

import logging
import os
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 5
DEFAULT_TIMEOUT = 300

# 思考の深さ。config ではなく定数で固定する（黙って変わらないように）。
# medium はユーザーの選択（2026-11-01）。同じ56名を high と比べ、合計点の差は平均 −0.09 点
# （同じ設定で採り直したときの揺れと同程度）だったので、○の基準はそのまま使える。
# Opus 5.5 の既定も medium だが、既定が変わっても黙って深さが変わらないよう明示する。
# 変えたら過去の応募者を再評価して点差と○の判定の変化を確かめる。
EFFORT = "medium"

# 1回の応答の上限（思考を含む）。上限で切れた応答は失敗として扱うので、十分大きく取る。
# 大きな上限は SDK がストリーミングを求めるため、stream() で受ける。
MAX_TOKENS = 64000

# 送り先は明示して固定する。省くと SDK は環境変数 ANTHROPIC_BASE_URL を使うため、
# Claude Code を中継サーバへ向ける設定をした瞬間に評価の送り先（とキー）も変わる。
BASE_URL = "https://api.anthropic.com"

# API キーの置き場。ユーザー環境変数 ANTHROPIC_API_KEY には置かない。
# Claude Code は非対話モード（claude -p）でその変数があれば常に使うため、
# この PC のすべての claude -p がプランではなく API 課金に切り替わってしまう。
# キーはユーザーが scripts\set-anthropic-key.ps1 で書く。Claude Code はこのファイルを開かない。
APP_DATA_DIR_NAME = "hrmos-auto-eval"
API_KEY_FILE_NAME = "anthropic-api-key"

# これに合わないキーは使わない。改行や全角文字が混ざったまま送ると、ヘッダーの組み立てに
# 失敗した例外文に値そのものが載りうる。Admin キー（sk-ant-admin）は Messages API を呼べない。
API_KEY_PATTERN = re.compile(r"sk-ant-[A-Za-z0-9_-]+")

# 本文を使ってよい終わり方。それ以外（refusal・max_tokens・pause_turn など）は失敗にする。
# 拒否も上限での途中切れも HTTP としては成功で返るので、本文だけ見ると欠けた評価を取り込む。
OK_STOP_REASONS = ("end_turn", "stop_sequence")

NO_KEY_MESSAGE = (
    "Claude API のキーが置かれていません。プロジェクトのフォルダで PowerShell を開き、\n"
    "  powershell -ExecutionPolicy Bypass -File scripts\\set-anthropic-key.ps1\n"
    "  を実行してキーを保存してください（キーは Claude Console で発行します）。"
)
BAD_KEY_MESSAGE = (
    "置かれている Claude API のキーの形が正しくありません"
    "（sk-ant- で始まる通常の API キーのはず。Admin キーは使えません）。"
    "scripts\\set-anthropic-key.ps1 で保存し直してください。"
)


class ClaudeApiClientError(Exception):
    """Claude API呼び出しエラー"""
    pass


def redact_api_keys(text: str) -> str:
    """文字列に混ざった API キーを伏せる。エラー文はログとメールに出るので、投げる前に必ず通す"""
    return API_KEY_PATTERN.sub("sk-ant-***", text)


def api_key_path() -> Path:
    """API キーのファイルの場所（%LOCALAPPDATA%\\hrmos-auto-eval\\anthropic-api-key）"""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_DATA_DIR_NAME / API_KEY_FILE_NAME


def read_api_key() -> str:
    """API キーを読む。無い・形が違うときは案内つきで失敗させる（値は文言に入れない）"""
    path = api_key_path()
    try:
        key = path.read_text(encoding="utf-8-sig").strip()
    except FileNotFoundError:
        raise ClaudeApiClientError(NO_KEY_MESSAGE) from None
    except OSError as e:
        # 「無い」以外の理由（権限など）を「置かれていません」と案内すると、
        # 置いてあるのに置き直させることになる
        raise ClaudeApiClientError(
            f"Claude API のキーのファイルを読めませんでした: {path}（{e.strerror}）"
        ) from None

    if not key:
        raise ClaudeApiClientError(NO_KEY_MESSAGE)
    if key.startswith("sk-ant-admin") or not API_KEY_PATTERN.fullmatch(key):
        raise ClaudeApiClientError(BAD_KEY_MESSAGE)
    return key


def _create_client(api_key: str, timeout: float):
    """SDK のクライアントを作る（テストで差し替える）

    SDK はアプリ全体では必須ではないため、ここで遅延 import する。依存を入れ直して
    いない環境でも、Gemini など他の provider の利用者まで import エラーで落とさない。
    """
    try:
        import anthropic
    except ImportError:
        raise ClaudeApiClientError(
            "Python パッケージ anthropic が入っていません。"
            ".venv\\Scripts\\python.exe -m pip install -r requirements.txt を実行してください。"
        ) from None

    # 自動リトライは切る。リトライは call_claude_api のループ（max_retries / retry_delay）に
    # 一本化し、待ち時間がログに見える形にする。
    return anthropic.Anthropic(
        api_key=api_key,
        base_url=BASE_URL,
        max_retries=0,
        timeout=timeout,
    )


def _stop_problem(stop_reason: str | None, refusal_category: str | None) -> str | None:
    """本文を使ってはいけない終わり方なら、その説明を返す（使ってよければ None）"""
    if stop_reason in OK_STOP_REASONS:
        return None
    if stop_reason == "refusal":
        # 別のモデルで自動でやり直さない（API の fallbacks を付けない）。採点するモデルが
        # 黙って変わると、取り消せない自動NG登録の判断に別モデルの点数が混ざるため
        return f"Claude が評価を断りました（区分: {refusal_category or '不明'}）"
    return f"Claude API の応答が途中で終わりました（stop_reason: {stop_reason or '記録なし'}）"


def _extract_text(message) -> str:
    """応答から本文を取り出す（思考ブロックは除く）"""
    return "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()


def _api_error_detail(error) -> str:
    """API のエラー本文から、人が読む説明だけを取り出す（言い換えない）

    本文は {"type": "error", "error": {"type": ..., "message": ...}} の形。
    残高不足のときに Console で何をすればよいかが埋もれないよう、中の説明を出す。
    """
    body = getattr(error, "body", None)
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        inner = body["error"]
        message = inner.get("message")
        if isinstance(message, str) and message:
            kind = inner.get("type")
            return f"{kind}: {message}" if isinstance(kind, str) and kind else message
    return str(getattr(error, "message", "") or error)


# 応答の途中で届くエラーのうち、再試行で回復しうる種類。応答の受信中に error イベントが
# 届くと、SDK はその時点の HTTP ステータス（200）で例外を作るため、ステータスだけでは
# 一時的な混雑と見分けられない（anthropic/_streaming.py で確認）
RETRYABLE_ERROR_TYPES = ("overloaded_error", "api_error", "rate_limit_error")


def _is_retryable_status(status: int) -> bool:
    """再試行で回復しうる HTTP ステータスか（429 混雑・408・5xx（529 過負荷を含む））"""
    return status in (408, 429) or status >= 500


def _is_retryable(error) -> bool:
    """再試行で回復しうる API エラーか（ステータスか、本文のエラーの種類で判断する）"""
    return _is_retryable_status(error.status_code) or error.type in RETRYABLE_ERROR_TYPES


def call_claude_api(prompt: str, config: dict) -> str:
    """Claude API を呼び出し、応答本文を返す"""
    eval_config = config.get("evaluation", {})
    max_retries = eval_config.get("max_retries", DEFAULT_MAX_RETRIES)
    retry_delay = eval_config.get("retry_delay", DEFAULT_RETRY_DELAY)
    timeout = eval_config.get("timeout", DEFAULT_TIMEOUT)
    # モデルは config で必ず明示する（validate_config が "claude-" で始まる正式名を求める）
    model = eval_config.get("model")

    client = _create_client(read_api_key(), timeout)
    import anthropic  # _create_client が成功していれば入っている

    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.debug(f"Claude API呼び出し (試行 {attempt}/{max_retries}, model={model})")
            with client.messages.stream(
                model=model,
                max_tokens=MAX_TOKENS,
                output_config={"effort": EFFORT},
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                message = stream.get_final_message()

        except anthropic.APIStatusError as e:
            # 応答の途中で届いたエラーは HTTP 200 になるので、そう分かるように書く
            where = "応答の途中" if e.status_code == 200 else f"HTTP {e.status_code}"
            error = ClaudeApiClientError(redact_api_keys(
                f"Claude API エラー ({where}): {_api_error_detail(e)}"
            ))
            if not _is_retryable(e):
                # 400（残高不足を含む）・401・403・404 などは再試行しても回復しない
                raise error from None
            last_error = error
            logger.warning(f"  {where}のエラー (試行 {attempt}/{max_retries})")
        except anthropic.APITimeoutError:
            last_error = ClaudeApiClientError(f"Claude API タイムアウト ({timeout}秒)")
            logger.warning(f"  タイムアウト (試行 {attempt}/{max_retries})")
        except anthropic.APIConnectionError as e:
            last_error = ClaudeApiClientError(
                redact_api_keys(f"Claude API 通信エラー: {e.message}")
            )
            logger.warning(f"  通信エラー (試行 {attempt}/{max_retries})")
        except Exception as e:
            # SDK が包むのは送信時の失敗だけで、受信途中の切断や読み取りタイムアウトは
            # 通信ライブラリ（httpx2）の例外のまま出てくる。分類できない失敗もここで
            # キーを伏せてから扱い、再試行する
            last_error = ClaudeApiClientError(
                redact_api_keys(f"Claude API 呼び出し中のエラー: {type(e).__name__}: {e}")
            )
            logger.warning(f"  受信中のエラー {type(e).__name__} (試行 {attempt}/{max_retries})")

        else:
            text = _extract_text(message)
            # 本文より先に終わり方を見る。拒否・途中切れは再試行せず失敗にする
            category = getattr(message.stop_details, "category", None)
            problem = _stop_problem(message.stop_reason, category)
            if problem:
                if text:
                    # 会話は保存されないため、拒否の理由を後から調べられるよう本文を残す
                    # （CLI の経路で ParseError の応答全文を data/logs/ に出しているのと同じ扱い）
                    logger.warning(f"  使わなかった応答の本文（{len(text)}字）:\n{text}")
                raise ClaudeApiClientError(problem)

            usage = message.usage
            # 費用の実測に使う（見積もりは仮説なので、実際のトークン数を残す）
            logger.info(
                f"  Claude API: model={message.model} effort={EFFORT} "
                f"入力 {usage.input_tokens} / 出力 {usage.output_tokens} トークン"
            )
            if text:
                return text
            last_error = ClaudeApiClientError("Claude API が空の応答を返しました")
            logger.warning(f"  空の応答 (試行 {attempt}/{max_retries})")

        if attempt < max_retries:
            logger.info(f"  {retry_delay}秒後にリトライ...")
            time.sleep(retry_delay)

    raise last_error or ClaudeApiClientError("Claude API呼び出しに失敗しました")
