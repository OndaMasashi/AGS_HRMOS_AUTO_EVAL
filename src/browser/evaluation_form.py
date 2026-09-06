"""HRMOS 選考評価フォームへの書き込み - 自動NG評価登録

HRMOS の画面に書き込むのはこのモジュールだけ。navigator.py は読み取り専用の
まま保つ（誤って評価を登録し得る経路を1箇所に閉じ込めるため）。

登録した評価は HRMOS の選考タイムラインに残り、取り消せない場合がある。
そのため判断に迷う状況では必ず「登録しない」側に倒す:
  - 応募日時が読めない       → UNKNOWN_DATE（登録しない）
  - 応募日時が古い           → TOO_OLD（登録しない）
  - 「選考を評価」ボタンが無い → NO_FORM（登録しない）
  - 操作の途中で失敗した      → FAILED（登録しない・画面を保存する）
"""

import asyncio
import logging
import re
from datetime import datetime

from playwright.async_api import Locator, Page

from src.browser.navigator import dump_debug_artifacts
from src.browser.page_utils import goto_with_retry
from src.browser.selectors import ApplicantDetailSelectors

logger = logging.getLogger(__name__)

# 処理結果。applicants.hrmos_eval_status にそのまま保存する
SUBMITTED = "submitted"        # 登録した
DRY_RUN = "dry_run"            # 登録直前まで確認した（未登録）
TOO_OLD = "too_old"            # 応募日時が対象期間より古い
NO_FORM = "no_form"            # 評価フォームを開けない（選考が締め切られている等）
UNKNOWN_DATE = "unknown_date"  # 応募日時を読み取れなかった
FAILED = "failed"              # 送信前に失敗した（登録されていない）
SUBMIT_UNCERTAIN = "submit_uncertain"  # 送信したが登録できたか確認できなかった

# 再実行しても結果が変わらない状態。ここに入る応募者は次回以降スキップする。
#   - dry_run / failed / unknown_date は「登録されていない」ことが確かなので再試行する
#   - no_form は「選考が締め切られた」と「描画が間に合わなかった」を区別できないため
#     再試行する。対象は応募 max_age_days 日以内に限られるので、締め切り済みの応募者を
#     何度も見に行き続けることにはならない（日が経てば too_old で確定する）
#   - submit_uncertain は登録済みかもしれないため、絶対に再試行しない（二重登録の防止）。
#     人が HRMOS のタイムラインを見て判断する
FINAL_STATUSES = frozenset({SUBMITTED, TOO_OLD, SUBMIT_UNCERTAIN})

# 「評価を登録」を押した後、フォームが閉じるのを待つ上限（秒）。
# 固定待ちで打ち切ると、応答が遅いだけの成功を失敗と誤判定する
SUBMIT_CLOSE_WAIT_SEC = 8

# 「応募日時  2026/9/1 18:22」からの抽出。ラベルと値の DOM 構造は HRMOS 側の
# 変更で崩れやすいため、要素を指さずページ全体のテキストから拾う。
# 時刻は省略されることがあるので任意扱いにする。
# ラベル文字列は selectors.py に集約する規約に従い、そこから組み立てる。
_APPLIED_AT_PATTERN = re.compile(
    re.escape(ApplicantDetailSelectors.APPLIED_AT_LABEL_TEXT)
    + r"[\s　]*[:：]?[\s　]*"
      r"(\d{4})/(\d{1,2})/(\d{1,2})"
      r"(?:[\s　]+(\d{1,2}):(\d{2}))?"
)


def parse_applied_at(page_text: str) -> datetime | None:
    """ページのテキストから応募日時を取り出す。読み取れなければ None を返す。

    純粋関数（ブラウザに触らない）にしてあるのは、書式変更で壊れたときに
    実機なしで切り分けられるようにするため。
    """
    if not page_text:
        return None

    match = _APPLIED_AT_PATTERN.search(page_text)
    if not match:
        return None

    hour = int(match.group(4)) if match.group(4) else 0
    minute = int(match.group(5)) if match.group(5) else 0
    try:
        return datetime(
            int(match.group(1)), int(match.group(2)), int(match.group(3)), hour, minute
        )
    except ValueError:
        # 書式は合っているが日付として成立しない（2026/13/45 等）
        return None


async def submit_ng_evaluation(
    page: Page,
    applicant_url: str,
    comment: str,
    *,
    max_age_days: int = 3,
    dry_run: bool = False,
    config: dict | None = None,
) -> tuple[str, datetime | None]:
    """応募者ページで「選考を評価」→ NG → コメント →「評価を登録」を行う。

    Args:
        applicant_url: 応募者個別ページの完全URL（applicants.page_url）
        comment: 総合評価コメント欄に入れる文言
        max_age_days: 応募日時がこの日数以内の応募者だけを対象にする
        dry_run: True なら「評価を登録」を押さずキャンセルする（登録しない）
        config: 失敗時の画面保存先を決めるために使う。None なら保存しない

    Returns:
        (処理結果, 応募日時)。応募日時が読めなかった場合は (UNKNOWN_DATE, None)。
        例外は外に投げない（AI評価の結果を巻き戻さないため）。
    """
    applied_at = None
    try:
        # 添付ダウンロードで履歴書ページへ移動しているため、詳細ページに戻る
        await goto_with_retry(page, applicant_url)

        applied_at = await _read_applied_at(page)
        if applied_at is None:
            logger.warning(
                f"  応募日時を読み取れないためNG登録をスキップします（現在URL: {page.url}）"
            )
            return UNKNOWN_DATE, None

        elapsed_days = (datetime.now() - applied_at).days
        if elapsed_days > max_age_days:
            logger.info(
                f"  NG登録の対象外: 応募日時 {applied_at:%Y-%m-%d %H:%M}"
                f"（{elapsed_days}日前 / 上限 {max_age_days}日）"
            )
            return TOO_OLD, applied_at

        evaluate_button, reason = await _find_evaluate_button(page)
        if evaluate_button is None:
            # 描画が間に合っていないだけの可能性があるので一度だけ待って探し直す
            await asyncio.sleep(2)
            evaluate_button, reason = await _find_evaluate_button(page)
        if evaluate_button is None:
            # 評価を入力できない応募者。異常ではないので画面の保存はせずログだけ残す
            logger.info(f"  NG登録をスキップします: {reason}")
            return NO_FORM, applied_at

        await evaluate_button.click()
        await asyncio.sleep(1)

        if not await _select_ng_radio(page):
            logger.error("  総合評価のNGを選択できませんでした")
            await _dump_screen(page, config, "ng_radio_not_found")
            await _try_cancel(page)
            return FAILED, applied_at

        if not await _fill_comment(page, comment):
            logger.error("  総合評価コメントの入力欄が見つかりませんでした")
            await _dump_screen(page, config, "ng_comment_not_found")
            await _try_cancel(page)
            return FAILED, applied_at

        if dry_run:
            logger.info(
                f"  [dry-run] 登録直前まで確認しました（未登録 / "
                f"応募日時 {applied_at:%Y-%m-%d %H:%M}）"
            )
            await _try_cancel(page)
            return DRY_RUN, applied_at

        submit_button = await _find_clickable(
            page, ApplicantDetailSelectors.SUBMIT_BUTTON_NAME
        )
        if submit_button is None:
            logger.error("  「評価を登録」ボタンが見つかりませんでした")
            await _dump_screen(page, config, "ng_submit_not_found")
            await _try_cancel(page)
            return FAILED, applied_at

        await submit_button.click()

        # フォームが閉じたことをもって登録成功とみなす。閉じるまで待つのは、
        # 応答が遅いだけの成功を失敗と誤判定しないため
        if not await _wait_form_closed(page):
            # ここは「登録されたかどうか分からない」状態。押した後なので登録済みの
            # 可能性があり、再試行すると二重登録になる。再試行しない状態として
            # 記録し、人がHRMOSのタイムラインで確認する
            logger.error(
                f"  「評価を登録」を押しましたが {SUBMIT_CLOSE_WAIT_SEC} 秒待っても"
                "フォームが閉じませんでした。登録できたか確認できないため、"
                "この応募者は再試行しません。HRMOSの選考タイムラインを確認してください"
            )
            await _dump_screen(page, config, "ng_form_still_open")
            return SUBMIT_UNCERTAIN, applied_at

        logger.info(
            f"  HRMOSにNG評価を登録しました（応募日時 {applied_at:%Y-%m-%d %H:%M}）"
        )
        return SUBMITTED, applied_at

    except Exception as e:
        logger.error(f"  NG登録の操作でエラー: {type(e).__name__}: {e}")
        await _dump_screen(page, config, "ng_form_error")
        await _try_cancel(page)
        return FAILED, applied_at


async def _read_applied_at(page: Page) -> datetime | None:
    """応募日時を読む。描画が間に合わない場合に備えて一度だけ読み直す"""
    for attempt in (1, 2):
        try:
            applied_at = parse_applied_at(await page.inner_text("body"))
        except Exception as e:
            logger.debug(f"  ページテキストを取得できませんでした: {type(e).__name__}")
            applied_at = None

        if applied_at is not None:
            return applied_at
        if attempt == 1:
            await asyncio.sleep(2)
    return None


async def _find_clickable(page: Page, name: str) -> Locator | None:
    """ボタンを探す。role=button で見つからなければテキストで探す。無ければ None"""
    button = page.get_by_role("button", name=name)
    if await button.count() > 0:
        return button.first

    text = page.get_by_text(name, exact=True)
    if await text.count() > 0:
        return text.first

    return None


async def _check_or_click(radio: Locator) -> bool:
    """ラジオを選ぶ。選べたら True

    入力要素が視覚的に隠されている UI では check が通らないため、クリックでも試す。
    """
    try:
        await radio.check()
        await asyncio.sleep(0.5)
        return True
    except Exception as e:
        logger.debug(f"  NGラジオの選択に失敗（クリックで再試行）: {type(e).__name__}")

    try:
        await radio.click()
        await asyncio.sleep(0.5)
        return True
    except Exception as e:
        logger.debug(f"  NGラジオのクリックにも失敗: {type(e).__name__}")

    return False


async def _find_evaluate_button(page: Page) -> tuple[Locator | None, str | None]:
    """「選考を評価」を探す。押せるなら (ボタン, None)、押せないなら (None, 理由)

    HRMOS ではこのボタンはアンカー要素（<a class="sg-button">）で role が付かず、
    既に自分が評価を入力した応募者では disabled 属性が付く。disabled のまま
    click しても何も起きず、フォームが開かないまま後続が失敗するため、
    押す前に押せるかどうかを判定する。
    """
    button = page.locator(ApplicantDetailSelectors.EVALUATE_BUTTON_CSS).filter(
        has_text=ApplicantDetailSelectors.EVALUATE_BUTTON_NAME
    )
    count = await button.count()
    if count == 0:
        # クラス名が変わった場合に備えて表示文字でも探す
        button = page.get_by_text(
            ApplicantDetailSelectors.EVALUATE_BUTTON_NAME, exact=True
        )
        count = await button.count()

    if count == 0:
        return None, "「選考を評価」が見つかりません（選考が締め切られている可能性）"
    if count > 1:
        return None, f"「選考を評価」の候補が {count} 件あり特定できません"
    if await button.first.get_attribute("disabled") is not None:
        return None, "「選考を評価」が無効です（すでに評価が入力済みの可能性）"

    return button.first, None


async def _select_ng_radio(page: Page) -> bool:
    """総合評価の「NG」を選ぶ。選べたら True

    候補が1件に絞れないときは選ばない。誤って「S」「A」「B」を選ぶと、
    意図と正反対の評価を登録することになる。
    """
    candidates = (
        # value は S / A / B / NG の4値。NG だけを狙うのに最も確実
        ("value属性", page.locator(ApplicantDetailSelectors.NG_RADIO_VALUE_CSS)),
        # exact=True を付けないと部分一致になり他の選択肢にも当たる
        ("ラベル全文", page.get_by_role(
            "radio", name=ApplicantDetailSelectors.NG_RADIO_NAME, exact=True
        )),
        # role が付かない形に変わった場合に備えて表示文字でも探す
        ("表示文字", page.get_by_text(
            ApplicantDetailSelectors.NG_RADIO_NAME, exact=True
        )),
    )
    for label, locator in candidates:
        count = await locator.count()
        if count == 0:
            continue
        if count > 1:
            logger.warning(
                f"  NGの候補が {count} 件あり特定できないため選択しません（{label}）"
            )
            continue
        if await _check_or_click(locator.first):
            return True

    logger.debug("  NGのラジオを特定できませんでした")
    return False


async def _fill_comment(page: Page, comment: str) -> bool:
    """総合評価コメント欄に文言を入れる。入れられたら True

    欄を1つに特定できないときは書き込まない。fill() は既存の内容を消してから
    書くため、社内メモ欄など別の入力欄に当たると他人の記入内容を失わせる。
    """
    # 実機では textarea[name="summary"]。読み上げ用のラベルは付いていないため
    # CSS を本命にし、name 属性が変わった場合にアクセシブル名で探し直す
    box = page.locator(ApplicantDetailSelectors.COMMENT_TEXTAREA_CSS)
    count = await box.count()
    if count == 0:
        box = page.get_by_role(
            "textbox", name=ApplicantDetailSelectors.COMMENT_TEXTAREA_NAME
        )
        count = await box.count()

    if count != 1:
        logger.error(
            f"  総合評価コメント欄を1つに特定できませんでした（候補 {count} 件）"
        )
        return False

    await box.first.click()
    await box.first.fill(comment)
    await asyncio.sleep(0.5)
    return True


async def _form_is_open(page: Page) -> bool:
    """評価フォームが開いたままか（「評価を登録」ボタンの有無で判定）"""
    submit_button = await _find_clickable(page, ApplicantDetailSelectors.SUBMIT_BUTTON_NAME)
    return submit_button is not None


async def _wait_form_closed(page: Page) -> bool:
    """評価フォームが閉じるまで待つ。閉じたら True、時間切れなら False"""
    for _ in range(SUBMIT_CLOSE_WAIT_SEC):
        await asyncio.sleep(1)
        if not await _form_is_open(page):
            return True
    return False


async def _try_cancel(page: Page) -> None:
    """開いたフォームを閉じる（閉じられなくても処理は続ける）"""
    try:
        cancel = await _find_clickable(page, ApplicantDetailSelectors.CANCEL_BUTTON_NAME)
        if cancel is not None:
            await cancel.click()
            await asyncio.sleep(0.5)
    except Exception as e:
        logger.debug(f"  評価フォームを閉じられませんでした: {type(e).__name__}")


async def _dump_screen(page: Page, config: dict | None, label: str) -> None:
    """失敗時の画面を保存する（config が無ければ何もしない）"""
    if config is None:
        return
    await dump_debug_artifacts(page, config, label)
