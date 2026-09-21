"""環境自己診断 - 導入後に「実際に動くか」を項目ごとに検証する

インストーラの最終ステップおよびトラブル時の切り分けに使う。
各チェックは「コマンドが成功したか」ではなく「目的物が実際に使えるか」を見る。
"""

import os
import sys
import unicodedata
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

OK = "OK"
WARN = "WARN"
NG = "NG"

# 診断用の最小プロンプト（本番の評価プロンプトは使わずコストを抑える）
PING_PROMPT = 'Reply with exactly this JSON and nothing else: {"evaluations":[],"ok":true}'

# 実運用で現れる上限の目安。年齢帯がここまで届いていなければ取りこぼしとみなす
EXPECTED_MAX_AGE = 60


def _check_python() -> tuple[str, str, str]:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info < (3, 10):
        return NG, f"Python {version}", "Python 3.10 以上が必要です。3.13 系の導入を推奨します。"
    # Microsoft Store のスタブ経由で動いていないか（実体のないエイリアス）
    if "WindowsApps" in sys.executable:
        return NG, f"Python {version}", (
            "Microsoft Store のエイリアス経由で実行されています。"
            "python.org または winget 版を導入し直してください。"
        )
    return OK, f"Python {version}", sys.executable


def _check_venv() -> tuple[str, str, str]:
    venv_python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        return NG, "仮想環境 (.venv)", "未作成です。setup\\install.bat を実行してください。"
    running_in_venv = Path(sys.executable).resolve() == venv_python.resolve()
    if not running_in_venv:
        return WARN, "仮想環境 (.venv)", (
            f"存在しますが、今は別のPythonで実行中です ({sys.executable})。"
            " .venv\\Scripts\\python.exe から実行してください。"
        )
    return OK, "仮想環境 (.venv)", str(venv_python)


def _check_packages() -> tuple[str, str, str]:
    required = {
        "playwright": "playwright",
        "pdfplumber": "pdfplumber",
        "docx": "python-docx",
        "openpyxl": "openpyxl",
        "yaml": "pyyaml",
        "resend": "resend",
    }
    missing = []
    for module, package in required.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    if missing:
        return NG, "依存パッケージ", (
            f"未導入: {', '.join(missing)} — "
            ".venv\\Scripts\\pip.exe install -r requirements.txt を実行してください。"
        )
    return OK, "依存パッケージ", f"{len(required)}件すべて導入済み"


def _check_chromium() -> tuple[str, str, str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return NG, "Chromium ブラウザ", "playwright が未導入です。"

    try:
        with sync_playwright() as p:
            executable = p.chromium.executable_path
    except Exception as e:
        return NG, "Chromium ブラウザ", f"Playwright の初期化に失敗: {e}"

    if not executable or not Path(executable).exists():
        return NG, "Chromium ブラウザ", (
            "未導入です。.venv\\Scripts\\python.exe -m playwright install chromium "
            "を実行してください。"
        )
    return OK, "Chromium ブラウザ", executable


def _check_config(config_path: str) -> tuple[str, str, str, dict | None]:
    path = Path(config_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        return NG, "設定ファイル", f"{path} がありません。setup\\install.bat を実行してください。", None

    # load_config() は認証情報が未設定でも例外を投げるため、ここでは使わない。
    # 「YAMLとして壊れている」と「認証情報が未入力」は原因も対処も違うので、
    # 混ぜて報告すると利用者が何を直せばよいか分からなくなる。
    import yaml

    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        return NG, "設定ファイル", (
            f"YAMLとして読めません（全角スペースの混入や引用符の閉じ忘れが多い原因です）: "
            f"{str(e).splitlines()[0]}"
        ), None
    except OSError as e:
        return NG, "設定ファイル", f"読み込めません: {e}", None

    if not isinstance(config, dict):
        return NG, "設定ファイル", "内容が空です。config.yaml.example から作り直してください。", None

    # 見出しだけ残して中身が空のセクションを均す（setdefault では None を潰せない）
    from src.config import normalize_config, validate_config

    normalize_config(config)

    # 認証情報は環境変数で上書きされるため、ここで反映しておく
    for env_name, key in (("HRMOS_EMAIL", "email"), ("HRMOS_PASSWORD", "password")):
        value = os.environ.get(env_name)
        if value:
            config["credentials"][key] = value
    if os.environ.get("RESEND_API_KEY"):
        config["email"]["api_key"] = os.environ["RESEND_API_KEY"]

    # 本番と同じ検証を使う。ここで OK なのに scan が落ちる状態を作らないため。
    errors = validate_config(config)
    if errors:
        return NG, "設定ファイル", errors[0] + (
            f"（他 {len(errors) - 1} 件）" if len(errors) > 1 else ""
        ), config

    criteria = config.get("evaluation_criteria") or []
    if not config.get("first_pass_criteria"):
        return WARN, "設定ファイル", (
            f"{path.name} / 評価基準 {len(criteria)}項目 — "
            "first_pass_criteria が未設定のため「1次通過候補」欄が全員空欄になります。"
        ), config

    return OK, "設定ファイル", f"{path.name} / 評価基準 {len(criteria)}項目", config


def _check_credentials(config: dict | None) -> tuple[str, str, str]:
    if config is None:
        return NG, "HRMOS認証情報", "設定ファイルが読めないため判定できません。"
    creds = config.get("credentials") or {}
    email = creds.get("email", "")
    if not email or not creds.get("password"):
        return NG, "HRMOS認証情報", (
            "未設定です。setup\\install.bat を実行して入力するか、環境変数 "
            "HRMOS_EMAIL / HRMOS_PASSWORD を設定してください（設定後は新しい画面で実行）。"
        )
    source = "環境変数" if os.environ.get("HRMOS_EMAIL") else "config.yaml"
    masked = email[:3] + "***@" + email.split("@")[-1] if "@" in email else "***"
    return OK, "HRMOS認証情報", f"{masked} ({source}から取得)"


def _check_llm(config: dict | None) -> tuple[str, str, str]:
    if config is None:
        return NG, "AI評価の疎通", "設定ファイルが読めないため判定できません。"

    provider = config.get("evaluation", {}).get("provider", "claude")

    # 疎通確認は短いプロンプト・短いタイムアウトで行う
    probe_config = {
        "evaluation": {
            **config.get("evaluation", {}),
            "max_retries": 1,
            "timeout": 120,
        }
    }

    from src.evaluator.llm_client import call_llm, LLMClientError

    try:
        response = call_llm(PING_PROMPT, probe_config)
    except LLMClientError as e:
        first_line = str(e).splitlines()[0]
        hint = ""
        if provider == "claude" and "unknown option" in str(e):
            # 評価時に付ける起動オプション（--no-session-persistence 等）を
            # 古い CLI が認識できない場合
            hint = " Claude CLI が古い可能性があります。claude update で更新してください。"
        elif provider == "claude":
            hint = " claude を一度手で起動してブラウザ認証を完了してください。"
        elif provider == "gemini_api":
            hint = " 環境変数 GEMINI_API_KEY と、キーの課金設定を確認してください。"
        return NG, f"AI評価の疎通 ({provider})", f"{first_line}{hint}"

    if not response.strip():
        return NG, f"AI評価の疎通 ({provider})", "空の応答が返りました。"

    detail = f"応答を受信 ({len(response)}文字)"
    if provider == "gemini_api":
        # 無料枠かどうかはAPIから判別できないため、毎回目に入る形で注意を出す
        detail += " ※APIキーの課金が有効か確認してください（無料枠は入力内容が学習に使われます）"
    return OK, f"AI評価の疎通 ({provider})", detail


def _check_data_dirs() -> tuple[str, str, str]:
    required = ["data/downloads", "data/reports", "data/logs"]
    created = []
    for rel in required:
        d = PROJECT_ROOT / rel
        if not d.exists():
            try:
                d.mkdir(parents=True, exist_ok=True)
                created.append(rel)
            except OSError as e:
                return NG, "データディレクトリ", f"{rel} を作成できません: {e}"

    probe = PROJECT_ROOT / "data" / ".write_test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as e:
        return NG, "データディレクトリ", f"data/ に書き込めません: {e}"

    note = f" (新規作成: {', '.join(created)})" if created else ""
    return OK, "データディレクトリ", f"書き込み可能{note}"


def _check_email(config: dict | None) -> tuple[str, str, str]:
    if config is None:
        return WARN, "メール通知", "設定ファイルが読めないため判定できません。"
    email_config = config.get("email", {})
    if not email_config.get("enabled"):
        return OK, "メール通知", "無効 (enabled: false) — 任意機能のため問題ありません"
    if not email_config.get("api_key"):
        return NG, "メール通知", (
            "有効ですが Resend APIキーが未設定です。"
            "環境変数 RESEND_API_KEY を設定してください。"
        )
    recipients = [t for t in email_config.get("to", []) if t]
    if not recipients:
        return NG, "メール通知", "有効ですが宛先 (email.to) が空です。"
    return OK, "メール通知", f"有効 / 宛先 {len(recipients)}件"


def _first_pass_age_gaps(first_pass_criteria: list) -> list[str]:
    """1次通過基準の年齢帯にある隙間・取りこぼしを列挙する

    どの帯にも入らない年齢の応募者は点数に関わらず「判定不能」になり、
    自動NG登録の対象から外れる（＝人が手で見るまで放置される）。
    """
    ranges = []
    for criteria in first_pass_criteria:
        if not isinstance(criteria, dict):
            continue
        age_range = criteria.get("age_range")
        if isinstance(age_range, (list, tuple)) and len(age_range) == 2:
            try:
                ranges.append((int(age_range[0]), int(age_range[1])))
            except (TypeError, ValueError):
                continue
    if not ranges:
        return []

    ranges.sort()
    gaps = []
    for (_, prev_end), (next_start, _) in zip(ranges, ranges[1:]):
        if next_start > prev_end + 1:
            gaps.append(f"{prev_end + 1}〜{next_start - 1}歳")

    # 開始年齢で並べているため、末尾の帯が最大の上限を持つとは限らない
    highest = max(end for _, end in ranges)
    if highest < EXPECTED_MAX_AGE:
        gaps.append(f"{highest + 1}歳以上")
    return gaps


def _check_hrmos_evaluation(config: dict | None) -> tuple[str, str, str]:
    if config is None:
        return WARN, "HRMOS自動NG登録", "設定ファイルが読めないため判定できません。"

    ng_config = config.get("hrmos_evaluation", {})
    if not isinstance(ng_config, dict):
        return NG, "HRMOS自動NG登録", (
            "hrmos_evaluation: の書き方が正しくありません"
            "（enabled: / dry_run: を字下げして並べてください）。"
        )
    if not ng_config.get("enabled"):
        return OK, "HRMOS自動NG登録", "無効 (enabled: false) — 任意機能のため問題ありません"

    first_pass_criteria = config.get("first_pass_criteria", [])
    if not first_pass_criteria:
        return NG, "HRMOS自動NG登録", (
            "有効ですが first_pass_criteria（1次通過の判定基準）が未設定です。"
            "全員が判定不能となり1件も登録されません。"
        )

    mode = "dry-run（登録しません）" if ng_config.get("dry_run", True) else "本番登録"
    detail = (
        f"有効 / {mode} / 上限 {ng_config.get('max_per_run', 20)}件 / "
        f"応募 {ng_config.get('max_age_days', 3)}日以内"
    )

    gaps = _first_pass_age_gaps(first_pass_criteria)
    if gaps:
        return WARN, "HRMOS自動NG登録", (
            f"{detail} ※first_pass_criteria の年齢帯に隙間があります（{'、'.join(gaps)}）。"
            "この年齢の応募者は判定不能となり登録対象から外れます。"
        )
    return OK, "HRMOS自動NG登録", detail


def _display_width(text: str) -> int:
    """全角文字を2桁として数えた表示幅を返す（コンソールの桁揃え用）"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def _pad(text: str, width: int) -> str:
    """表示幅を揃えるために右側を空白で埋める"""
    return text + " " * max(0, width - _display_width(text))


def run_doctor(config_path: str = "config.yaml", skip_llm: bool = False) -> int:
    """環境診断を実行し、問題があれば終了コード1を返す"""
    # Chromium の確認で使う Playwright のドライバは、インタプリタ終了時に
    # 「Task was destroyed but it is pending!」等の後片付け警告を ERROR ログで出す。
    # 診断結果とは無関係だが利用者には異常に見えるため、このコマンドの間は黙らせる。
    # （診断が終わった後に出力されるので、一時的に下げて戻す方式では消せない）
    import logging

    logging.getLogger("asyncio").setLevel(logging.CRITICAL)

    print("=" * 62)
    print("  HRMOS AI評価ツール - 環境診断")
    print("=" * 62)
    print()

    results = [
        _check_python(),
        _check_venv(),
        _check_packages(),
        _check_chromium(),
    ]

    status, name, detail, config = _check_config(config_path)
    results.append((status, name, detail))
    results.append(_check_credentials(config))
    results.append(_check_data_dirs())
    results.append(_check_email(config))
    results.append(_check_hrmos_evaluation(config))

    if skip_llm:
        results.append((WARN, "AI評価の疎通", "--skip-llm 指定のためスキップしました"))
    else:
        print("  AI評価の疎通を確認中（実際にリクエストを1回送ります）...")
        results.append(_check_llm(config))
        print()

    label_width = max(_display_width(name) for _, name, _ in results) + 2
    ng_count = 0
    warn_count = 0

    for status, name, detail in results:
        if status == NG:
            ng_count += 1
        elif status == WARN:
            warn_count += 1
        print(f"  [{status:<4}] {_pad(name, label_width)} {detail}")

    print()
    print("-" * 62)
    if ng_count:
        print(f"  異常 {ng_count}件 / 警告 {warn_count}件 — 上記の指示に従って解消してください。")
        return 1
    if warn_count:
        print(f"  警告 {warn_count}件 — 動作はしますが確認を推奨します。")
        return 0
    print("  すべて正常です。run_scan.bat で実行できます。")
    return 0
