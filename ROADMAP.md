# ROADMAP

今後のタスク一覧。完了したものは詳細を `improvement_list/` に記録し、ここにはリンクのみ残す。

## 未対応タスク

### 中: スリープ解除タイマーが OS 側で無効なため `WakeToRun` が効かない

タスクスケジューラの `HRMOS_AutoEval_1230` / `_1730` に `WakeToRun=True` を設定したが、OS のスリープ解除タイマーが AC/DC とも無効（`powercfg /query SCHEME_CURRENT SUB_SLEEP RTCWAKE` → `0x00000000`）のため実際には PC を起こせない。有効化するとシステム全体で他タスクも PC を起こせるようになるため、電源設定を変えるかは要判断。`StartWhenAvailable=True` により復帰後の実行は担保済み。

根拠: [2026-07-29 ページ遷移のリトライ導入とスケジューラ設定の修正](improvement_list/2026-07-29_fix_navigation_timeout_and_scheduler.md)

### 中: `setup_scheduler.bat` を再実行するとスリープ対策設定が失われる

同バッチは `schtasks /Create` で既存タスクを削除して作り直すため、2026-07-29 に設定した `StartWhenAvailable` / `WakeToRun` / バッテリー条件が既定値に戻る。再登録のたびに手で設定し直す運用は事故のもとなので、バッチ側に PowerShell での設定追加を組み込むのが望ましい。該当: `setup_scheduler.bat`

### 中: AI 評価が拒否された応募者が 11 名残っている

2026-07-28 17:30 の実行で Claude CLI が `I'm not going to run this evaluation.` / `I'm not able to act on this one.` を返し、JSON パースに失敗。プロンプト側の要因か CLI 側の一時的挙動かは未調査。`python run.py scan --retry-errors` で再試行可能。

### 低: `documents` テーブルに重複行が蓄積する

再評価のたびに同じ添付が重複 INSERT される。集計や参照を行う機能を追加する際は重複排除が前提になる。

### 低: 既存テストが実行できない状態になっている

`tests/test_pii_masker.py` に pytest ベースのユニットテストがあるが、pytest が `requirements.txt` にも `.venv` にも入っておらず実行できない。まず依存に追加して復旧させ、そのうえでパーサ・評価 JSON のパースなど副作用のない層へ広げるのが現実的。該当: `requirements.txt` / `tests/`

### 低: リポジトリルートに不要な生成物が残っている

`nul`（78 バイト、Windows 予約名で誤生成されたファイル）と `cworkAGS_HRMOS_AUTO_EVALtests`（パス指定ミスで作られた空ディレクトリ）が残っている。実害はないが紛らわしい。削除には `del \\?\%CD%\nul` のような特殊な指定が必要。

## 完了タスク

- [2026-07-29 ページ遷移のリトライ導入とスケジューラ設定の修正](improvement_list/2026-07-29_fix_navigation_timeout_and_scheduler.md)
- [2026-06-10 セッション判定の強化と診断ダンプ](improvement_list/2026-06-10_strengthen_session_check_and_debug_dump.md)
- [2026-06-06 アーキテクチャ図の追加](improvement_list/2026-06-06_アーキテクチャ図の追加.md)
- [2026-06-04 新規0件通知・失敗アラートの追加](improvement_list/2026-06-04_notify_no_candidates_and_failure.md)
- [2026-06-02 メール通知の評価内訳・経歴書添付](improvement_list/2026-06-02_email_breakdown_resume_attachment_link.md)
- [2026-03-10 スケジューラとログ出力の修正](improvement_list/2026-03-10_fix_scheduler_and_logging.md)
