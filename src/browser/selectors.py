"""
HRMOS採用ページのセレクタ定義

playwright codegen で取得した実際のセレクタに基づく。
Playwright locator API（get_by_role, get_by_text等）を使用。
"""


class LoginSelectors:
    """ログインページ（2段階: メール → 続行 → パスワード → ログイン）"""
    EMAIL_INPUT_ROLE = "textbox"
    EMAIL_INPUT_NAME = "メールアドレス"
    CONTINUE_BUTTON_NAME = "続行"

    PASSWORD_INPUT_ROLE = "textbox"
    PASSWORD_INPUT_NAME = "パスワード"
    LOGIN_BUTTON_NAME = "ログイン"


class ApplicantListSelectors:
    """応募者一覧ページ"""
    # 各応募者はリンク要素。テキストにステータス・名前・大学名等を含む
    # 例: " 書類選考 / 評価未入力 玉井 晴香 / 成城大学 ..."
    APPLICANT_LINK_ROLE = "link"


class ApplicantDetailSelectors:
    """応募者個別ページ"""
    # 履歴書・職務経歴書セクションを開くリンク
    RESUME_SECTION_LINK_TEXT = "履歴書・職務経歴書の確認"
    # ダウンロードアイコン（空テキストのリンク）
    DOWNLOAD_LINK_ROLE = "link"
