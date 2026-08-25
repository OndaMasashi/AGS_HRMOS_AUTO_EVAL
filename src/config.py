"""設定管理 - config.yaml読み込みと環境変数のフォールバック"""

import os
from pathlib import Path

import yaml


def normalize_config(config: dict) -> dict:
    """見出しだけ書かれて中身が空のセクションを空辞書に整える

    YAML では `credentials:` と書いて中身を消すと None になる。
    そのまま辞書として扱うと TypeError で落ちるため、先に均しておく。
    """
    for key in ("credentials", "email", "evaluation", "scan", "interview_questions"):
        if config.get(key) is None:
            config[key] = {}
    return config


def validate_config(config: dict) -> list[str]:
    """設定内容を検証し、問題点のリストを返す（例外は投げない）

    doctor と load_config の両方から呼ぶ。ここを唯一の検証箇所にすることで
    「doctor は OK なのに scan が起動直後に落ちる」状態を防ぐ。
    """
    if not isinstance(config, dict):
        return ["config.yaml の内容が空です。config.yaml.example から作り直してください。"]

    errors = []

    creds = config.get("credentials")
    if creds is not None and not isinstance(creds, dict):
        errors.append(
            "credentials: の書き方が正しくありません（email: / password: を字下げして並べてください）。"
        )

    criteria = config.get("evaluation_criteria")
    if not criteria:
        errors.append("evaluation_criteria（評価基準）が未設定です。")
    elif not isinstance(criteria, list):
        errors.append("evaluation_criteria はリスト（- name: ... の並び）で書いてください。")
    else:
        for i, c in enumerate(criteria, 1):
            if not isinstance(c, dict):
                errors.append(f"evaluation_criteria の {i} 番目の書き方が正しくありません。")
            elif not c.get("name") or not c.get("description"):
                errors.append(
                    f"evaluation_criteria の {i} 番目に name と description の両方が必要です。"
                )

    return errors


def load_config(config_path: str = "config.yaml") -> dict:
    """設定ファイルを読み込み、環境変数で上書きする"""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"設定ファイルが見つかりません: {config_path}\n"
            "config.yaml.example をコピーして config.yaml を作成してください。"
        )

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        raise ValueError(
            "config.yaml の内容が空です。config.yaml.example から作り直してください。"
        )
    normalize_config(config)

    # 環境変数で認証情報を上書き
    env_email = os.environ.get("HRMOS_EMAIL")
    env_password = os.environ.get("HRMOS_PASSWORD")
    if env_email:
        config["credentials"]["email"] = env_email
    if env_password:
        config["credentials"]["password"] = env_password

    # 環境変数でResend APIキーを上書き
    env_resend_key = os.environ.get("RESEND_API_KEY")
    if env_resend_key:
        config.setdefault("email", {})["api_key"] = env_resend_key

    # 認証情報の検証
    if not config["credentials"].get("email") or not config["credentials"].get("password"):
        raise ValueError(
            "認証情報が設定されていません。\n"
            "config.yaml の credentials セクション、または環境変数 "
            "HRMOS_EMAIL / HRMOS_PASSWORD を設定してください。"
        )

    # 内容の検証（doctor と同じ関数を使い、判定が食い違わないようにする）
    errors = validate_config(config)
    if errors:
        raise ValueError(
            "config.yaml の内容に問題があります:\n  - " + "\n  - ".join(errors)
        )

    return config
