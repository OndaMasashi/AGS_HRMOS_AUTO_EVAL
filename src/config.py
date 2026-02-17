"""設定管理 - config.yaml読み込みと環境変数のフォールバック"""

import os
from pathlib import Path

import yaml


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

    # 環境変数で認証情報を上書き
    env_email = os.environ.get("HRMOS_EMAIL")
    env_password = os.environ.get("HRMOS_PASSWORD")
    if env_email:
        config["credentials"]["email"] = env_email
    if env_password:
        config["credentials"]["password"] = env_password

    # 認証情報の検証
    if not config["credentials"].get("email") or not config["credentials"].get("password"):
        raise ValueError(
            "認証情報が設定されていません。\n"
            "config.yaml の credentials セクション、または環境変数 "
            "HRMOS_EMAIL / HRMOS_PASSWORD を設定してください。"
        )

    return config
