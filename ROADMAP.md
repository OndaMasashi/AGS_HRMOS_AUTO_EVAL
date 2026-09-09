# ROADMAP

今後のタスク一覧。完了したものは詳細を `improvement_list/` に記録し、ここにはリンクのみ残す。

## 未対応タスク

### 高: ○の基準を引き上げる（方針決定済み・数値は検討中）

直近3か月で266人中139人（52%）が○になっており、ハードルを上げる方針。
**年齢帯ごとの偏りも無くす方向で調整する**（現状 20-24歳 66.7% / 35-39歳 31.2% と2倍の開き）。

**先に知っておくべき落とし穴**: 平均点は7項目の平均なので **0.143 刻みの値しか取らない**。
そのため `min_avg_score` を 0.1 動かしても人数が変わらない区間がある。
現行設定では `3.9` と `4.0` が**実質同じ判定**（どちらも「4.0以上」）になっており、
50-54歳と55-59歳で別基準にしているつもりが同じ基準で動いていた。
同様に `2.4` は実質「2.43以上」、`2.9` は実質「3.0以上」。
**閾値は実際に取りうる値（k/7）に合わせて設定すること。**

検討材料（4月以降584人で算出。カッコ内はその閾値での通過率）:

| 年齢帯 | 人数 | 現行 | 現行○率 | 40%目標 | 35%目標 | 30%目標 | 25%目標 |
|---|---|---|---|---|---|---|---|
| 20-24 | 81 | 2.0 | 66.7% | 2.29(40%) | 2.29(40%) | 2.43(28%) | 2.57(27%) |
| 25-29 | 249 | 2.4 | 49.8% | 2.57(37%) | 2.57(37%) | 2.71(29%) | 2.71(29%) |
| 30-34 | 72 | 2.9 | 37.5% | 3.00(38%) | 3.00(38%) | 3.14(26%) | 3.14(26%) |
| 35-39 | 32 | 3.3 | 31.2% | 3.29(38%) | 3.29(38%) | 3.43(31%) | 3.57(22%) |
| 40-44 | 20 | 3.5 | 45.0% | 3.71(40%) | 3.86(35%) | 3.86(35%) | 4.00(25%) |
| 45-49 | 34 | 3.7 | 47.1% | 3.86(35%) | 3.86(35%) | 3.86(35%) | 4.00(24%) |
| 50-54 | 47 | 3.9 | 42.6% | 4.00(43%) | 4.14(28%) | 4.14(28%) | 4.14(28%) |
| 55-59 | 39 | 4.0 | 35.9% | 3.86(44%) | 4.00(36%) | 4.00(36%) | 4.14(23%) |

一律で上げる場合は +0.1 で○率52%→42%、+0.2 で32%、+0.3 で26%（直近3か月266人）。

**未決**: 目標とする通過率。決まれば `config.yaml` の `first_pass_criteria` を書き換えるだけ。
なお `hrmos_evaluation` が有効なため、**基準を上げると自動NG登録の対象者も増える**点に注意。

### 低: PII マスキングの取りこぼし（主要分は対応済み）

2026-09-09 に氏名・メールアドレス・郵便番号を対応済み（氏名 6人→0人、メール 18件→0件）。
残っているのは以下の2つ。いずれも機微度は下がっており、優先度は低い。

- **ラベルのない生年月日**: 「生年月日」等のラベルが近くにある日付だけを対象にしているため、
  ラベルなしで書かれた生年月日は残る。職歴の年月日（在籍期間の評価に必要）を巻き込まないための制限
- **郵便番号の変則表記**: 20人中5件が残存（スペース区切りなど想定外の書式）

詳細は [改修履歴](improvement_list/2026-09-09_fix_llm_model_drift.md)。

### 中: 評価がモデルに拒否されるケースがある

再評価の検証20人中1人で、モデルが「採否に関わる評価は意図確認なしには実行しない」と回答し、
JSON を返さず `ParseError` になった。本番でも同じ拒否が起こり得る。
`applicants` の `status='error'`（現在15件）との関連は未確認。
まずエラー15件の内訳を調べ、拒否が含まれるならプロンプト側で用途と正当性を明示する。

### 低: 評価モデルの変更時は過去との連続性を確認する

2026-09-09 に `evaluation.model` を `opus` に確定した（再評価の実測で 5〜6月当時の採点との差が
sonnet +0.214 / opus +0.143 と、opus のほうが過去の評価との連続性が高かったため）。
`config.yaml` は git 管理外なので、**モデルを変えるときはこの行を更新して履歴を残すこと**。
変更後は過去の応募者を再評価して点差を測り、○率が動かないか確認する
（手順は [改修履歴](improvement_list/2026-09-09_fix_llm_model_drift.md) の「再評価による裏付け」）。

### 高: 登録した評価を取り消す方法が未確認

2026-09-06 に本番登録を1件（田辺 正邦）試して成功した。ただし登録後の画面を調べたところ、
**選考タイムライン上に「編集」「削除」「取り消し」の導線が見当たらなかった**。
「選考・面談」タブなど別画面や、管理者権限での可否は未確認。

**誤登録しても元に戻せない前提で運用する**か、取り消し方法を確認してから対象を広げること。

なお HRMOS 側にも重複防止がある。**自分が一度評価を入力すると「選考を評価」ボタンが無効
（`disabled`）になる**（実測で確認）。ツール側の `hrmos_eval_status` による抑止と二重に効く。


### 中: 自動NG登録の稼働状況をしばらく見る

2026-09-07 に本番運用へ切り替え、同日 17:30 の定期実行で**初回の自動登録が正常に動いた**
（4名を評価し × の1名だけ登録／失敗0件）。設計どおりに動くことは確認できたが、
サンプルが1回のみのため、しばらくはメール通知の内訳を見ておく。

- **「失敗」が0でなければ** `data/debug/` の `ng_*` を見てセレクタの破損を疑う
- 想定と違う件数が登録されていたら `config.yaml` の `dry_run` を `true` に戻せば登録だけ止まる
- **登録は取り消せない**ため、異常に気づくのが遅れるほど影響が広がる

初回の結果は [改修履歴](improvement_list/2026-09-06_hrmos_auto_ng_evaluation.md) に記録。


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

`tests/` にユニットテストが2件（`test_pii_masker.py` / `test_first_pass.py`、計30ケース超）あるが、pytest が `requirements.txt` にも `.venv` にも入っておらず実行できない。**自動NG登録の判定ロジックを守るテストが動かない状態**なので、まず依存に追加して復旧させ、そのうえでパーサ・評価 JSON のパースなど副作用のない層へ広げるのが現実的。該当: `requirements.txt` / `tests/`


### 低: リポジトリルートに不要な生成物が残っている

`nul`（78 バイト、Windows 予約名で誤生成されたファイル）と `cworkAGS_HRMOS_AUTO_EVALtests`（パス指定ミスで作られた空ディレクトリ）が残っている。実害はないが紛らわしい。削除には `del \\?\%CD%\nul` のような特殊な指定が必要。

## 完了タスク

- [2026-09-06 HRMOSへの自動NG評価登録](improvement_list/2026-09-06_hrmos_auto_ng_evaluation.md) — 判定不能（年齢不明・年齢帯外）と不合格の区別、`first_pass_criteria` の年齢帯の穴埋めもここで解消
- [2026-08-25〜26 インストーラ刷新・Gemini APIキー経路・配布物とドキュメントの整備](improvement_list/2026-08-25_installer_rebuild_and_gemini_api.md) — `setup_scheduler.bat` 再実行でスリープ対策設定が失われる問題、`config.yaml.example` の `first_pass_criteria` 欠落、配布物への機密混入もここで解消
- [2026-07-29 ページ遷移のリトライ導入とスケジューラ設定の修正](improvement_list/2026-07-29_fix_navigation_timeout_and_scheduler.md)
- [2026-06-10 セッション判定の強化と診断ダンプ](improvement_list/2026-06-10_strengthen_session_check_and_debug_dump.md)
- [2026-06-06 アーキテクチャ図の追加](improvement_list/2026-06-06_アーキテクチャ図の追加.md)
- [2026-06-04 新規0件通知・失敗アラートの追加](improvement_list/2026-06-04_notify_no_candidates_and_failure.md)
- [2026-06-02 メール通知の評価内訳・経歴書添付](improvement_list/2026-06-02_email_breakdown_resume_attachment_link.md)
- [2026-03-10 スケジューラとログ出力の修正](improvement_list/2026-03-10_fix_scheduler_and_logging.md)
