"""設定管理 - config.yaml読み込みと環境変数のフォールバック"""

import os
from pathlib import Path

import yaml


def normalize_config(config: dict) -> dict:
    """見出しだけ書かれて中身が空のセクションを空辞書に整える

    YAML では `credentials:` と書いて中身を消すと None になる。
    そのまま辞書として扱うと TypeError で落ちるため、先に均しておく。
    """
    for key in (
        "credentials", "email", "evaluation", "scan", "interview_questions",
        "hrmos_evaluation",
    ):
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

    errors.extend(_validate_hrmos_evaluation(config))

    return errors


def _validate_hrmos_evaluation(config: dict) -> list[str]:
    """HRMOSへの自動NG評価登録の設定を検証する

    HRMOS への書き込みは取り消せない場合があるため、設定の書き間違いで意図せず
    有効になったり、対象者が想定と食い違ったりしないよう厳しめに見る。
    """
    hrmos_eval = config.get("hrmos_evaluation")
    if hrmos_eval is None:
        return []
    if not isinstance(hrmos_eval, dict):
        return [
            "hrmos_evaluation: の書き方が正しくありません"
            "（enabled: / dry_run: を字下げして並べてください）。"
        ]

    errors = []

    # enabled が false のときも型を見る。true/false 以外（"false" のような文字列）
    # を書くと真と判定され、意図せず HRMOS へ書き込む状態になるため
    for key in ("enabled", "dry_run"):
        value = hrmos_eval.get(key)
        if value is not None and not isinstance(value, bool):
            errors.append(f"hrmos_evaluation.{key} は true か false で書いてください。")

    if hrmos_eval.get("enabled") is not True:
        return errors

    for key in ("max_per_run", "max_age_days"):
        value = hrmos_eval.get(key)
        if value is None:
            continue
        # bool は int のサブクラスなので、true と書かれた場合を先に弾く
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            errors.append(f"hrmos_evaluation.{key} は1以上の整数で書いてください。")

    comment = hrmos_eval.get("comment")
    if comment is not None and (not isinstance(comment, str) or not comment.strip()):
        errors.append(
            "hrmos_evaluation.comment には HRMOS の評価コメント欄に入れる文言を書いてください。"
        )

    if not config.get("first_pass_criteria"):
        errors.append(
            "hrmos_evaluation.enabled が true ですが first_pass_criteria が未設定です。"
            "全員が判定不能になり HRMOS へ1件も登録されません。"
            "年齢帯ごとの平均点しきい値を設定してください。"
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
