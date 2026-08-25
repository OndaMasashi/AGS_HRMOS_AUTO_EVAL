# ROADMAP

今後のタスク一覧。完了したものは詳細を `improvement_list/` に記録し、ここにはリンクのみ残す。

## 未対応タスク

### 最優先: 現行の Claude 運用が学習利用の対象になっていないか確認する

Claude Code 公式ドキュメント `https://code.claude.com/docs/en/data-usage`（2026-08-25 確認）:

> **Consumer users (Free, Pro, and Max plans)**: We will train new models using data from
> Free, Pro, and Max accounts **when this setting is on (including when you use Claude Code
> from these accounts).**

- つまり Pro/Max は「学習に使われない」のではなく **設定次第**。Gemini 無料枠を失格にしたのと
  同じ基準を当てるなら無条件合格ではない。
- 保持期間も設定で変わる: 学習利用を許可 → **5年**、許可しない → 30日。
- Team / Enterprise / API（商用条件）は既定で学習利用されない。

本ツールは `provider: "claude"` で本番稼働しており、DB に 1,913名・評価 5,229件が蓄積している。
設定が ON のまま稼働していた期間があれば、その間に送信した応募者の職歴・所属企業・資格・年齢・
性別が学習に使われた可能性がある。

確認すること:
1. `https://claude.ai/settings/data-privacy-controls` で現在の設定を確認する。
2. **「今 OFF にする」より先に「これまで ON だった期間があるか」を確認する**（過去分の扱いが変わる）。
3. ON だった期間があれば、社内の個人情報取扱い上の事象として記録・報告が必要か判断する。
4. Claude を継続利用する場合、運用PCで `DISABLE_FEEDBACK_COMMAND=1` と
   `CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY=1` を設定する（`/feedback` `/bug` `/share` の
   transcript 送信は保持5年）。


### 最優先: Gemini APIキーを auth key へ移行する（2026年9月に Standard キーが拒否される）

公式ドキュメント `https://ai.google.dev/gemini-api/docs/api-key` に次の記載がある（2026-08-25 確認）:

> On September 2026: the Gemini API will reject requests from Standard keys.
> You must migrate to auth keys before this date to avoid service interruption.

- キー種別は **Standard key**（プロジェクトに紐づく従来型）と **auth key**（Google Cloud
  サービスアカウントに直接バインドされる新型）の2種類。
- 現時点で既に「制限なしの Standard キー」は拒否済み。制限付き Standard キーは当面動くが、
  2026年9月に全 Standard キーが拒否される。
- **AI Studio で新規作成したキーは自動的に auth key になる**（"All new API keys created in
  Google AI Studio are automatically created as auth keys."）。
- **呼び出し方は変わらない**（`x-goog-api-key` ヘッダのまま）。よって
  `src/evaluator/gemini_api_client.py` のコード改修は不要。キーを差し替えるだけでよい。

対応: AI Studio の APIキー画面で「キーのタイプ」列を確認し、Standard のものは新規作成した
auth key に差し替える。差し替え後は環境変数 `GEMINI_API_KEY` を更新し、`run.py doctor` で疎通確認する。


### 高: Anthropic / OpenAI の利用ポリシー上「履歴書スクリーニング」は高リスク用途

Anthropic 利用ポリシーは resume screening を高リスク用途に指定し、有資格者による事前レビューを
要件としている。現行の「Excel を人が読んで判断する」運用は要件を満たすが、**将来「AI判定で自動
足切り」に発展させるとポリシー違反になる**。恒久的な設計制約として残す。


### 高: 新インストーラの「素のWindows 11」実機検証が未実施

`install.bat` / `install.ps1` を新規作成したが、Python 未導入のPCでの自動インストール経路
（winget → python.org フォールバック、PATH 未反映時の再実行案内）は開発機では通っていない。
配布前に1台で必ず確認すること。該当: `install.ps1`

根拠: [2026-08-25 インストーラ刷新と Gemini APIキー経路](improvement_list/2026-08-25_installer_rebuild_and_gemini_api.md)


### 高: Gemini APIキーの課金を有効化する（無料枠のままだと応募者情報が学習に使われる）

2026-08-25 の実機確認で、Workspace アカウントでも AI Studio で APIキーを作成できるが
**請求階層が「無料枠」** のままだった。無料枠は「入力内容を製品改善に利用する」規約のため、
応募者の職務経歴書を送る本ツールでは使用不可。配布前に AI Studio の「お支払い情報を設定」から
課金を有効化すること。**ツール側で無料枠かどうかを検知する仕組みは無い**ため、人手の確認に依存する。

根拠: [2026-08-25 インストーラ刷新と Gemini APIキー経路](improvement_list/2026-08-25_installer_rebuild_and_gemini_api.md)


### 中: 旧配布zip `AGS_HRMOS_AUTO_EVAL_dist.zip` が Git 管理下に残っている

2026-03-03 時点の内容で、現行のインストーラも `src/browser/page_utils.py` も含まないため、
誤って配布すると起動直後に ImportError で落ちる。`setup/build_dist.ps1` に置き換え済みなので
`git rm` を推奨。該当: リポジトリルート


### 中: 既存の定期実行タスクは再登録が必要

`run_scan.bat` に無人モード（引数 `scheduled`）を追加したため、**それ以前に登録したタスクには
引数が付いておらず、実行のたびに `pause` で黒い画面が残り続ける**。
`setup\setup_scheduler.bat` を再実行して登録し直すこと。

根拠: [2026-08-25 インストーラ刷新と Gemini APIキー経路](improvement_list/2026-08-25_installer_rebuild_and_gemini_api.md)


### 中: スリープ解除タイマーが OS 側で無効なため `WakeToRun` が効かない

タスクスケジューラの `HRMOS_AutoEval_1230` / `_1730` に `WakeToRun=True` を設定したが、OS のスリープ解除タイマーが AC/DC とも無効（`powercfg /query SCHEME_CURRENT SUB_SLEEP RTCWAKE` → `0x00000000`）のため実際には PC を起こせない。有効化するとシステム全体で他タスクも PC を起こせるようになるため、電源設定を変えるかは要判断。`StartWhenAvailable=True` により復帰後の実行は担保済み。

根拠: [2026-07-29 ページ遷移のリトライ導入とスケジューラ設定の修正](improvement_list/2026-07-29_fix_navigation_timeout_and_scheduler.md)


### 中: AI 評価が拒否された応募者が 11 名残っている

2026-07-28 17:30 の実行で Claude CLI が `I'm not going to run this evaluation.` / `I'm not able to act on this one.` を返し、JSON パースに失敗。プロンプト側の要因か CLI 側の一時的挙動かは未調査。`python run.py scan --retry-errors` で再試行可能。


### 低: `config.yaml` の `max_text_chars` が参照されていない

`config.yaml` に `max_text_chars: 80000` があるが `src/` から一度も参照されず、実際の切り詰めは
`src/evaluator/claude_client.py` のハードコード定数で行われる。**config を書き換えても動作が
変わらない**（対策したつもりで無防備になるサイレント失敗）。該当: `config.yaml.example` / `prompt_builder.py`


### 低: `run.py scan --all` に確認ゲートがない

全応募者を再評価するため、1回の実行で HRMOS へ登録人数分のアクセスが発生し数時間かかる。
実行前に「対象N名・推定所要時間」を表示して確認を求め、`--yes` でスキップできるゲートが望ましい。
該当: `run.py` / `src/main.py`


### 低: `documents` テーブルに重複行が蓄積する

再評価のたびに同じ添付が重複 INSERT される。集計や参照を行う機能を追加する際は重複排除が前提になる。


### 低: 既存テストが実行できない状態になっている

`tests/test_pii_masker.py` に pytest ベースのユニットテストがあるが、pytest が `requirements.txt` にも `.venv` にも入っておらず実行できない。まず依存に追加して復旧させ、そのうえでパーサ・評価 JSON のパースなど副作用のない層へ広げるのが現実的。該当: `requirements.txt` / `tests/`


### 低: リポジトリルートに不要な生成物が残っている

`nul`（78 バイト、Windows 予約名で誤生成されたファイル）と `cworkAGS_HRMOS_AUTO_EVALtests`（パス指定ミスで作られた空ディレクトリ）が残っている。実害はないが紛らわしい。削除には `del \\?\%CD%\nul` のような特殊な指定が必要。

## 完了タスク

- [2026-08-25〜26 インストーラ刷新・Gemini APIキー経路・配布物とドキュメントの整備](improvement_list/2026-08-25_installer_rebuild_and_gemini_api.md) — `setup_scheduler.bat` 再実行でスリープ対策設定が失われる問題、`config.yaml.example` の `first_pass_criteria` 欠落、配布物への機密混入もここで解消
- [2026-07-29 ページ遷移のリトライ導入とスケジューラ設定の修正](improvement_list/2026-07-29_fix_navigation_timeout_and_scheduler.md)
- [2026-06-10 セッション判定の強化と診断ダンプ](improvement_list/2026-06-10_strengthen_session_check_and_debug_dump.md)
- [2026-06-06 アーキテクチャ図の追加](improvement_list/2026-06-06_アーキテクチャ図の追加.md)
- [2026-06-04 新規0件通知・失敗アラートの追加](improvement_list/2026-06-04_notify_no_candidates_and_failure.md)
- [2026-06-02 メール通知の評価内訳・経歴書添付](improvement_list/2026-06-02_email_breakdown_resume_attachment_link.md)
- [2026-03-10 スケジューラとログ出力の修正](improvement_list/2026-03-10_fix_scheduler_and_logging.md)
