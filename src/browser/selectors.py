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

    # 一覧が実際に描画されたかの判定に使う CSS セレクタ。
    # 単なる /interviews/ ではナビゲーション等のリンクを誤検知するため、
    # 応募者個別ページ（/interviews/screening/<id> 等）に限定する。
    # NOTE: 収集時の判定は navigator._is_applicant_link 側にあり、取りこぼしを
    # 避けるため意図的にこれより広い（/interviews/ 全般を許容）。
    APPLICANT_LINK_CSS = (
        'a[href*="/interviews/screening/"], '
        'a[href*="/candidates/"], '
        'a[href*="/applicants/"]'
    )


class ApplicantDetailSelectors:
    """応募者個別ページ"""
    # 履歴書・職務経歴書セクションを開くリンク
    RESUME_SECTION_LINK_TEXT = "履歴書・職務経歴書の確認"
    # ダウンロードアイコン（空テキストのリンク）
    DOWNLOAD_LINK_ROLE = "link"

    # --- 応募日時（自動NG登録の対象期間の判定に使う） ---
    # 画面上は「応募日時  2026/9/1 18:22」の形で出る。ラベルと値のDOM構造は
    # HRMOS 側の変更で崩れやすいため、要素を指さずページテキストから正規表現で
    # 抜き出す（抽出は evaluation_form.parse_applied_at）。
    APPLIED_AT_LABEL_TEXT = "応募日時"

    # --- 選考評価フォーム（書き込み系。自動NG登録でのみ使う） ---
    # 2026-09-06 に実機のDOMを採取して確定した値。HRMOS は Angular Material 製で、
    # 評価フォームは応募者ページ内に展開される（別ウィンドウではない）。
    #
    # フォームを開くボタン: <a hrm-button class="sg-button"> 選考を評価 </a>
    # button 要素ではなくアンカーで、role="button" が付かない。そのため
    # get_by_role("button") では引けず、テキストか下のCSSで探す必要がある。
    # 既に自分が評価を入力した応募者では disabled 属性が付いて押せなくなる。
    EVALUATE_BUTTON_NAME = "選考を評価"
    EVALUATE_BUTTON_CSS = "a.sg-button, button.sg-button"

    # 総合評価のラジオ: <mat-radio-button> の中に
    #   <input type="radio" name="mat-radio-group-0" value="NG"> が入る。
    # value は S / A / B / NG の4値で、NG だけを狙うには value 指定が最も確実。
    # アクセシブル名（ラベル全文）でも1件に引ける。
    NG_RADIO_NAME = "NG - 基準を下回っている"
    NG_RADIO_VALUE_CSS = 'input[type="radio"][value="NG"]'

    # 総合評価コメント: <textarea name="summary">。
    # aria-label 等が無くアクセシブル名では引けないため name 属性で指定する。
    # 単に "textarea" だと将来ページ内に他の複数行入力が増えたとき誤爆する。
    COMMENT_TEXTAREA_NAME = "総合評価コメント"
    COMMENT_TEXTAREA_CSS = 'textarea[name="summary"]'

    # 送信・中止: どちらも <button class="sg-button">（登録は type="submit"）
    SUBMIT_BUTTON_NAME = "評価を登録"
    CANCEL_BUTTON_NAME = "キャンセル"
