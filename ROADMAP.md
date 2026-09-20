# ROADMAP

今後のタスク一覧。完了したものは詳細を `improvement_list/` に記録し、ここにはリンクのみ残す。

## 未対応タスク

### 最優先: Gemini APIキーを auth key へ移行する（**期限到来済み**）

公式ドキュメント `https://ai.google.dev/gemini-api/docs/api-key` に次の記載がある（2026-08-25 確認）:

> On September 2026: the Gemini API will reject requests from Standard keys.
> You must migrate to auth keys before this date to avoid service interruption.

**2026年9月に入っており期限が到来している。** 現在は `provider: "claude"` で運用しているため
即座の実害はないが、**Gemini へ切り替えようとした時点で動かない可能性がある**（障害時の退避先が
使えない状態）。切り替えを検討する前に確認すること。

- キー種別は **Standard key**（プロジェクトに紐づく従来型）と **auth key**（Google Cloud
  サービスアカウントに直接バインドされる新型）の2種類。
- **AI Studio で新規作成したキーは自動的に auth key になる**（"All new API keys created in
  Google AI Studio are automatically created as auth keys."）。
- **呼び出し方は変わらない**（`x-goog-api-key` ヘッダのまま）。よって
  `src/evaluator/gemini_api_client.py` のコード改修は不要。キーを差し替えるだけでよい。

対応: AI Studio の APIキー画面で「キーのタイプ」列を確認し、Standard のものは新規作成した
auth key に差し替える。差し替え後は環境変数 `GEMINI_API_KEY` を更新し、`run.py doctor` で疎通確認する。


### 高: 自動NG登録の稼働を見届ける（新しい○基準での初回を含む）

2026-09-07 に本番運用へ切り替え、同日 17:30 の初回登録は正常に動いた（4名を評価し × の1名だけ登録／失敗0件）。
ただし 2026-09-09 に `first_pass_criteria` を引き上げたため（○率 52%→35% 見込み）、
**△ だった応募者が × に落ちて登録対象が増える**。`dry_run: false` のまま運用に入っている。

- 次回の定期実行のメール通知で、内訳（登録／対象期間外／評価フォームなし／判定不能／失敗）が想定どおりか確認する
- **「失敗」が0でなければ** `data/debug/` の `ng_*` を見てセレクタの破損を疑う
- 想定より件数が多い場合は `config.yaml` の `dry_run` を `true` に戻せば登録だけ止まる
- **HRMOS への登録は取り消せない**ため、気づくのが遅れるほど影響が広がる

初回の結果は [自動NG登録の改修履歴](improvement_list/2026-09-06_hrmos_auto_ng_evaluation.md)、
閾値の決定根拠と通過率の試算は [採点ドリフトの改修履歴](improvement_list/2026-09-09_fix_llm_model_drift.md)。

### 高: 登録した評価を取り消す方法が未確認

2026-09-06 に本番登録を1件（田辺 正邦）試して成功した。ただし登録後の画面を調べたところ、
**選考タイムライン上に「編集」「削除」「取り消し」の導線が見当たらなかった**。
「選考・面談」タブなど別画面や、管理者権限での可否は未確認。

**誤登録しても元に戻せない前提で運用する**か、取り消し方法を確認してから対象を広げること。

なお HRMOS 側にも重複防止がある。**自分が一度評価を入力すると「選考を評価」ボタンが無効
（`disabled`）になる**（実測で確認）。ツール側の `hrmos_eval_status` による抑止と二重に効く。


### 高: 「履歴書スクリーニング」は利用規約上の高リスク用途（自動NG登録の運用で担保が必要）

Anthropic 利用ポリシーは resume screening を高リスク用途に指定し、有資格者による事前レビューを
要件としている。「Excel を人が読んで判断する」運用は要件を満たす。

2026-09-06 に、AI評価が○にならなかった応募者を HRMOS 上で自動的に NG 評価にする機能
（`hrmos_evaluation`、既定 OFF）を実装した。**有効にすると人が書類を見ないまま不合格が確定する**
ため、規約上の要件はツールでは担保できず、運用側で担保する必要がある:

- 有効化は採用責任者の承認を得てから行う
- 登録済みの応募者を定期的に人が抜き取り確認する
  （`SELECT * FROM applicants WHERE hrmos_eval_status = 'submitted'` で抽出できる）
- 誤登録に気づいたら HRMOS 上で評価を修正する

ツール側の安全弁: 既定 OFF ／ dry-run ／ 1実行あたりの上限件数 ／ 応募 3 日以内に限定 ／
年齢から判定できない応募者は対象外 ／ `--all` では登録しない ／ 登録済みは再登録しない。


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

**2026-09-09 追記**: 一時的挙動ではなく再現する。過去の応募者20人を再評価した検証でも1人で発生し、
モデルが「採否に関わる評価は意図確認なしには実行しない」と回答して JSON を返さなかった。
`applicants` の `status='error'` は現在15件。プロンプト側で用途と正当性（人が最終判断する運用であること）を
明示するのが対策の方向。詳細は [改修履歴](improvement_list/2026-09-09_fix_llm_model_drift.md)。


### 低: 自動NG登録に失敗した応募者を拾い直す経路がない

2026-09-15 に1件失敗した（原因は**セレクタの破損ではなくページ遷移のタイムアウト**。
画面は `data/debug/ng_form_error_20260915_174637_811854.png`）。
**この1件は再登録不要と判断済み**（2026-09-20）。以下は仕組みの話。

`failed` は `FINAL_STATUSES` に含まれないため再試行される設計だが、`_run_ng_evaluation()` は
**評価処理の中でしか呼ばれない**。失敗した応募者は `status='scanned'` になるため次回の
スキャン対象にならず、結果として**二度と試行されない**（`--retry-errors` は `status='error'`
が対象、`--all` は仕様上登録しない）。

実害は「自動で落とされなかった」だけで安全側のため優先度は低い。**当面は失敗が出たら
手動でHRMOSを操作する運用**とし、頻発するようなら `failed` / `no_form` だけを再試行する
コマンドの追加を検討する（評価は済んでいるので AI 呼び出しは不要）。


### 低: PII マスキングの取りこぼし（主要分は対応済み）

2026-09-09 に氏名・メールアドレス・郵便番号を対応済み（氏名 6人→0人、メール 18件→0件）。
残っているのは以下の2つ。いずれも機微度は下がっており、優先度は低い。

- **ラベルのない生年月日**: 「生年月日」等のラベルが近くにある日付だけを対象にしているため、
  ラベルなしで書かれた生年月日は残る。職歴の年月日（在籍期間の評価に必要）を巻き込まないための制限
- **郵便番号の変則表記**: 20人中5件が残存（スペース区切りなど想定外の書式）

詳細は [改修履歴](improvement_list/2026-09-09_fix_llm_model_drift.md)。


### 低: 評価モデルの変更時は過去との連続性を確認する

2026-09-09 に `evaluation.model` を `opus` に確定した（再評価の実測で 5〜6月当時の採点との差が
sonnet +0.214 / opus +0.143 と、opus のほうが過去の評価との連続性が高かったため）。
`config.yaml` は git 管理外なので、**モデルを変えるときはこの行を更新して履歴を残すこと**。
変更後は過去の応募者を再評価して点差を測り、○率が動かないか確認する
（手順は [改修履歴](improvement_list/2026-09-09_fix_llm_model_drift.md) の「再評価による裏付け」）。


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


### 低: テストの対象を広げる

2026-09-09 に pytest を開発機の `.venv` へ導入し、`test_pii_masker.py` に12件追加して**全56件が走る状態になった**
（`requirements.txt` には入れていない。配布先では不要なため）。
残りは副作用のない層への拡張: `parser/document.py`（PDF/Word/Excel のテキスト抽出）と
`evaluator/response_parser.py`（評価 JSON のパース・検証）。該当: `tests/`


### 低: Windows 予約名へのリダイレクトに注意

2026-09-09 に `nul` / `dist` / `cworkAGS_HRMOS_AUTO_EVALtests` を削除済み。
`nul` の中身は `ls` のエラー出力で、**Git Bash で `2> nul` と書いたことが原因**だった
（cmd.exe では捨てられるが、Git Bash では `nul` という名前のファイルが作られる）。
Git Bash では `2>/dev/null` を使うこと。削除は PowerShell から
`[System.IO.File]::Delete('\\?\<絶対パス>\nul')` で行う（通常の `Remove-Item` では消せない）。

## 完了タスク

- [2026-09-20 Claude の学習利用設定を確認](improvement_list/2026-09-20_claude_data_usage_check.md) — 結果は**対象外**。過去分も含め個人情報取扱い上の事象としての報告は不要と判断。プラン変更・別アカウントでの運用開始時は再確認が必要
- [2026-09-20 配布ドキュメントを自動NG登録・新しい○基準に同期](improvement_list/2026-09-20_setup_docs_sync.md) — `SETUP_GUIDE.ADVANCED.html` に自動NG登録の手順を新設、1次通過判定の4値化と閾値の丸めを全配布物へ反映
- [2026-09-09 評価モデルの明示指定とPIIマスキングの強化](improvement_list/2026-09-09_fix_llm_model_drift.md) — 「○が増えた」の原因調査（母集団の若返り＋採点ドリフト）、モデル無指定による採点の漂流、氏名・メールアドレスのマスク漏れ、○の閾値引き上げ（52%→35%）もここで対応
- [2026-09-06 HRMOSへの自動NG評価登録](improvement_list/2026-09-06_hrmos_auto_ng_evaluation.md) — 判定不能（年齢不明・年齢帯外）と不合格の区別、`first_pass_criteria` の年齢帯の穴埋めもここで解消
- [2026-08-25〜26 インストーラ刷新・Gemini APIキー経路・配布物とドキュメントの整備](improvement_list/2026-08-25_installer_rebuild_and_gemini_api.md) — `setup_scheduler.bat` 再実行でスリープ対策設定が失われる問題、`config.yaml.example` の `first_pass_criteria` 欠落、配布物への機密混入もここで解消
- [2026-07-29 ページ遷移のリトライ導入とスケジューラ設定の修正](improvement_list/2026-07-29_fix_navigation_timeout_and_scheduler.md)
- [2026-06-10 セッション判定の強化と診断ダンプ](improvement_list/2026-06-10_strengthen_session_check_and_debug_dump.md)
- [2026-06-06 アーキテクチャ図の追加](improvement_list/2026-06-06_アーキテクチャ図の追加.md)
- [2026-06-04 新規0件通知・失敗アラートの追加](improvement_list/2026-06-04_notify_no_candidates_and_failure.md)
- [2026-06-02 メール通知の評価内訳・経歴書添付](improvement_list/2026-06-02_email_breakdown_resume_attachment_link.md)
- [2026-03-10 スケジューラとログ出力の修正](improvement_list/2026-03-10_fix_scheduler_and_logging.md)
