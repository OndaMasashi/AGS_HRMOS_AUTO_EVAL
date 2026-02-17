"""
HRMOS採用ページのCSSセレクタ一元管理

重要: これらのセレクタは初回セットアップ時に `playwright codegen` で発見し、
実際のHRMOS UIに合わせて更新する必要があります。

セットアップ手順:
  1. playwright codegen https://hrmos.co を実行
  2. ブラウザでログイン → 応募者一覧 → 個別ページを操作
  3. 記録されたセレクタをここに転記

HRMOS UIが変更された場合も、このファイルのみ修正すれば対応できます。
"""


class LoginSelectors:
    """ログインページのセレクタ"""
    # TODO: playwright codegen で実際のセレクタを確認して更新
    EMAIL_INPUT = 'input[name="email"], input[type="email"]'
    PASSWORD_INPUT = 'input[name="password"], input[type="password"]'
    LOGIN_BUTTON = 'button[type="submit"]'
    # ログイン成功の判定要素（ダッシュボードなど）
    LOGIN_SUCCESS_INDICATOR = 'nav, [class*="dashboard"], [class*="header"]'


class ApplicantListSelectors:
    """応募者一覧ページのセレクタ"""
    # TODO: playwright codegen で実際のセレクタを確認して更新
    # 応募者行/カードのセレクタ
    APPLICANT_ROW = 'tr[class*="applicant"], [class*="candidate-row"], table tbody tr'
    # 応募者名リンク
    APPLICANT_LINK = 'a[href*="candidate"], a[href*="applicant"]'
    # 応募者名テキスト
    APPLICANT_NAME = 'td:first-child a, [class*="name"]'
    # ページネーション - 次ページボタン
    NEXT_PAGE_BUTTON = 'button[class*="next"], a[class*="next"], [aria-label="Next"]'
    # ページネーション - 次ページボタンが無効な場合の判定
    NEXT_PAGE_DISABLED = '[class*="next"][disabled], [class*="next"][class*="disabled"]'


class ApplicantDetailSelectors:
    """応募者個別ページのセレクタ"""
    # TODO: playwright codegen で実際のセレクタを確認して更新
    # 添付ファイルセクション
    ATTACHMENT_SECTION = '[class*="attachment"], [class*="file"], [class*="document"]'
    # 添付ファイルのダウンロードリンク
    ATTACHMENT_LINK = 'a[href*="download"], a[href*="attachment"], a[download]'
    # 添付ファイル名
    ATTACHMENT_NAME = '[class*="file-name"], [class*="filename"]'
    # 応募者名（詳細ページ上）
    DETAIL_NAME = 'h1, h2, [class*="candidate-name"], [class*="applicant-name"]'
