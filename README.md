# HRMOS採用 応募者書類AI評価ツール

HRMOS採用ページをクローリングし、応募者一覧から履歴書等の書類（PDF/Word/Excel）を自動ダウンロードし、AI が評価基準に基づいて各応募者を自動評価・スコアリングし、面接質問候補とともにExcelレポートを出力するCLIツールです。

> **このファイルは開発者向けです。配布物には含まれません。**
> 利用者向けの説明は `setup/` の3つのHTMLが正です。
>
> | ファイル | 内容 |
> |---|---|
> | [setup/SETUP_GUIDE.html](setup/SETUP_GUIDE.html) | 導入手順（受け取った人が読む） |
> | [setup/SETUP_GUIDE.ADVANCED.html](setup/SETUP_GUIDE.ADVANCED.html) | 設定変更（評価基準・1次通過ライン・自動NG登録など10項目） |
> | [setup/OVERVIEW.html](setup/OVERVIEW.html) | 機能とアーキテクチャの解説 |
> | [setup/DISTRIBUTION.md](setup/DISTRIBUTION.md) | 配る側の手順 |

## 主な機能

- 応募者書類の自動ダウンロード（PDF/Word/Excel対応）
- Gemini API / Claude CLI によるAI自動評価（設定した評価基準に基づく1〜5点のスコアリング、configで切替可能。使うモデルは `evaluation.model` で固定する）
- LLM送信前の個人情報マスキング（氏名・電話・住所・メールアドレス・郵便番号・生年月日の月日。職歴・企業名・資格は評価に必要なため残す）
- 面接質問候補の自動生成（応募者ごとに3問）
- Excel一覧表の自動出力（レーダーチャート・1次通過候補・備考欄付き）
- メール通知（Resend API、オプション。評価内訳付きサマリ・○のHRMOSリンク・1次通過候補の経歴書添付。加えて新規0件時の「新規なし」通知・スキャン失敗時のアラートで無音による見逃しを防止）
- 差分処理（未評価の応募者のみ自動処理）

## 動作環境

- **OS**: Windows 10/11
- **Python**: 3.10 以上（未導入なら `install.bat` が 3.13 を自動インストール）
- **ブラウザ**: Chromium（Playwrightが自動インストール）
- **AI**: 以下のいずれか
  - **Gemini API キー**（推奨 / `provider: "gemini_api"`）: CLI・Node.js・ブラウザログインが不要。[Google AI Studio](https://aistudio.google.com/apikey) でキーを発行する
  - **Claude Code**（`provider: "claude"`）: Pro / Max / Team / Enterprise / Console のいずれかの契約と、初回のブラウザ認証が必要

> **注意**: Gemini CLI（`provider: "gemini"`）は 2026-06-18 に個人アカウント向けの提供が終了したため、通常は動作しません。Gemini を使う場合は APIキー認証の `gemini_api` を選んでください。
>
> Gemini API の**無料枠は入力内容が製品改善に利用される規約**です。応募者の書類を扱うため、**課金を有効にしたプロジェクトのキー**を使用してください。
>
> **Google Workspace のライセンスでは Gemini API を利用できません。** Workspace に含まれるのは Gmail・ドキュメント等の画面内 Gemini のみで、API の利用枠は別契約です。API の階層は Google Cloud の請求先アカウントの有無だけで決まるため、**Workspace とは別に課金設定（カード登録）が必要**です。

## 導入に必要な準備（利用者側）

インストーラを実行する前に、以下を手元に用意してください。

| # | 準備するもの | 補足 |
|---|---|---|
| 1 | HRMOS採用のログインID / パスワード | インストーラが対話形式で聞きます |
| 2 | Gemini API キー **または** Claude の有料契約 | Gemini の場合は [AI Studio](https://aistudio.google.com/apikey) で発行（課金有効なプロジェクトのキー） |
| 3 | Resend APIキー（任意） | メール通知を使う場合のみ |
| 4 | インターネット接続 | 社内プロキシがある場合は `HTTPS_PROXY` の設定値 |

管理者権限は不要です（Python もツール本体もユーザースコープに入ります）。

## セットアップ手順

### かんたんセットアップ（推奨）

**Step 0**: 受け取った zip を**右クリック → プロパティ → 「セキュリティ」欄の「許可する」にチェック → OK**。
これを行わないと、展開後の `install.bat` が Windows のセキュリティ警告でブロックされます。

**Step 1**: zip を任意のフォルダに展開します。

**Step 2**: `setup\install.bat` をダブルクリックします。以下が自動で実行されます。

1. Python の確認（未導入なら winget または python.org から 3.13 を自動インストール）
2. 仮想環境 `.venv` の作成
3. 依存パッケージのインストール
4. Chromium のインストール
5. `config.yaml` の作成
6. **HRMOSのログイン情報・AIの設定を対話形式で入力**（Windowsのユーザー環境変数に保存）
7. 定期実行（平日 12:30 / 17:30）の登録（任意）
8. **自己診断** — 実際にAIへ1回リクエストを送り、動く状態かを確認

**Step 3**: 診断がすべて `OK` になれば完了です。`run_scan.bat` をダブルクリックで実行できます。

> Python を新規インストールした直後は「新しい画面で開き直してください」と表示されることがあります。異常ではありません（PATH の変更は新しく開いたウィンドウにしか反映されないため）。案内どおり `setup\install.bat` をもう一度実行してください。

### 導入後の確認・トラブル切り分け

いつでも次のコマンドで環境を再診断できます。

```powershell
.venv\Scripts\python.exe run.py doctor

# AIへのリクエストを送らずに確認する（APIコストを消費しない）
.venv\Scripts\python.exe run.py doctor --skip-llm
```

Python・仮想環境・依存パッケージ・Chromium・設定ファイル・認証情報・データフォルダ・メール通知・**AI評価の疎通**を1項目ずつ判定し、`NG` の行に対処方法を表示します。

### 認証情報の保存場所

`setup\install.bat` で入力した認証情報は **config.yaml ではなく Windows のユーザー環境変数**に保存されます（`HRMOS_EMAIL` / `HRMOS_PASSWORD` / `GEMINI_API_KEY`）。フォルダごとコピーしても認証情報が一緒に持ち出されないようにするためです。

手動で設定する場合:

```powershell
[Environment]::SetEnvironmentVariable('HRMOS_EMAIL', 'your-email@example.com', 'User')
[Environment]::SetEnvironmentVariable('HRMOS_PASSWORD', 'your-password', 'User')
[Environment]::SetEnvironmentVariable('GEMINI_API_KEY', 'AIza...', 'User')
[Environment]::SetEnvironmentVariable('RESEND_API_KEY', 're_xxxxx', 'User')
```

> 設定後は**新しいウィンドウを開いてから**実行してください（既存のウィンドウには反映されません）。

### 手動セットアップ

`setup\install.bat` を使わない場合は以下の手順です。

```powershell
python -m venv .venv
.venv\Scripts\pip.exe install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
copy config.yaml.example config.yaml
.venv\Scripts\python.exe run.py doctor
```

`config.yaml` を開いて `evaluation.provider`（`gemini_api` / `claude`）と `evaluation_criteria` を設定し、認証情報は上記の環境変数で指定します。

## 配布パッケージの作成（配る側）

```powershell
powershell -ExecutionPolicy Bypass -File setup\build_dist.ps1
```

`setup/AGS_HRMOS_AUTO_EVAL_YYYYMMDD.zip` が生成されます（同僚へ渡す3点が同じ場所に揃うよう、既定の出力先は `setup/` です）。Git 管理下のファイルを基準に組み立て、`config.yaml` / `storage_state.json` / `data/` などの機密・実行時生成物は自動で除外します。配布に必要なファイルが欠けている場合はエラーで停止します。

> 配布先には「zip を展開する前に、右クリック → プロパティ → 『許可する』にチェック」を必ず伝えてください。

## 使い方

### 日常の運用

**日々の実行はこのコマンドだけでOKです。** 書類ダウンロード → AI評価 → Excel出力まで自動で行われます。

```powershell
python run.py scan
```

前回評価済みの応募者は自動的にスキップされるため、**新規・未処理の応募者のみ**が対象になります。

### コマンド一覧

| コマンド                               | 説明                                       | 用途                         |
| -------------------------------------- | ------------------------------------------ | ---------------------------- |
| `python run.py scan`                 | AI評価実行＋Excelレポート自動出力          | **日常はこれだけ実行** |
| `python run.py scan --all`           | 全応募者を再評価（評価済みも含む）         | 評価基準変更時など           |
| `python run.py scan --dry-run`       | HRMOSへの自動NG登録をせず対象者だけ確認      | 自動NG登録の設定を変えた直後 |
| `python run.py report`               | DB内の過去全件の評価結果をExcel出力        | 過去データの再出力           |
| `python run.py report --run-id <ID>` | 特定回の評価結果のみExcel出力              | 特定回の結果だけ欲しいとき   |
| `python run.py status`               | 評価進捗状況を表示                         | 処理状況の確認               |

> **scan と report の違い**: `scan` はAI評価実行後にその回の結果を自動でExcelに出力します。`report` は評価は行わず、DBに蓄積された過去の結果をまとめて再出力するためのコマンドです。

### オプション

各コマンドに `-v` を付けるとデバッグログが出力されます。

```powershell
python run.py -v scan
```

## Excel出力フォーマット

1行 = 1応募者のマトリクス形式で出力されます。左側にサマリ情報、右側に詳細評価を配置したレイアウトです。

| 列 | 内容 |
|----|------|
| 応募者名 | 応募者のフルネーム |
| 性別 | 書類から読み取った性別（男性/女性/不明） |
| 年齢 | 書類から読み取った年齢 |
| HRMOS URL | 応募者の個別ページURL |
| ファイル名 | ダウンロードした書類名 |
| 1次通過候補 | 年齢帯×平均点閾値に基づく判定（○/△/×/？）。**セル自体が応募者ページへのリンク**。`？` は年齢不明・年齢帯外で**判定できなかった**ことを表し、点数が基準未満の `×` とは意味が違う |
| 平均点 | 合計点 ÷ 評価基準数（小数点1桁） |
| 合計点 | 全評価項目の合計スコア |
| 総合ランク | S/A/B/C/D（平均点ベース、色付き） |
| レーダーチャート | 各評価基準のスコアを塗りつぶしレーダーで可視化 |
| 総合評価 | AIによる総合評価コメント |
| {評価項目}(点) | 各評価基準のスコア（1〜5） |
| {評価項目}(評価) | 各評価基準の詳細コメント |
| 備考欄 | 評価基準では測れない特記事項（転職回数、ブランク期間等） |
| 質問候補1〜3 | 面接時の推奨質問 |

## メール通知（Resend）- オプション

> **この機能は任意です。** 設定しなくてもAI評価・レポート出力は通常通り動作します。メール通知が不要な場合は `email.enabled: false`（デフォルト）のままで問題ありません。

AI評価が完了した場合、結果をメールで自動通知します。本文には応募者ごとの評価サマリ表（年齢・1次通過候補・平均点・合計点・**各評価基準の点数とコメントの内訳**・総合評価）が含まれ、Excelレポートが添付されます。

- 表内の **「○」がHRMOS応募者ページへのリンク**になっており、クリックで候補者ページを開けます。
- **1次通過候補（○）の応募者の経歴書を添付**します（`email.attach_resumes`、デフォルト有効）。経歴書はマスクなしの個人情報を含むため、社内ポリシーを確認のうえ運用してください。添付したくない場合は `config.yaml` で `attach_resumes: false` を設定します。

### セットアップ

1. [Resend](https://resend.com) でアカウントを作成し、APIキーを取得
2. `config.yaml` の `email` セクションを設定

```yaml
email:
  enabled: true
  api_key: ""                # 環境変数 RESEND_API_KEY でも指定可
  from: "onboarding@resend.dev"
  to:
    - "宛先@example.com"
  subject_prefix: "[HRMOS]"
  attach_resumes: true       # 1次通過候補(○)の経歴書を添付（PII注意）
  notify_on_no_candidates: true  # 新規0件で正常終了した時も「新規なし」通知を送る（無音による誤認防止）
```

### 動作条件・通知の種類

`email.enabled: true` の場合、スキャン結果に応じて以下のいずれかが送信されます（無音で終わらないため「失敗したのか」の誤認を防げます）。

- **評価結果メール**: 新規応募者を1名以上評価できたとき（結果サマリ＋Excel添付）。評価できなかった応募者（AIが評価を断った・書類を読めなかった等）がいると、件名に「評価できず N名」、本文に名前・理由・HRMOSへのリンクが出る。この応募者は `status='error'` になり通常の scan では再評価されないため、HRMOSで直接評価する
- **「新規なし」通知**: 新規応募者が0名で正常終了したとき。`notify_on_no_candidates: true`（デフォルト）のときのみ送信（`false` で抑止可）
- **スキャン失敗アラート**: 認証失敗・応募者一覧の取得0件・対象はいたが評価成功0件・処理中の例外のとき（`email.enabled` のみで常時送信）

経歴書添付は `attach_resumes: true`（デフォルト）かつ○候補が存在する評価結果メールの場合のみ。

## HRMOSへの自動NG評価登録 - オプション（既定OFF）

> **この機能は初期状態で無効です。** 有効にすると、1次通過候補が「○」にならなかった応募者について、HRMOSの応募者ページで「選考を評価」→ NG →コメント入力→「評価を登録」までを自動で行います。

**【重要】AI各社の利用規約は採用選考を高リスク用途とし、有資格者による事前レビューを要件としています。** 有効にすると人が書類を見ないまま不合格が確定します。**登録した評価はHRMOSの選考タイムラインに残り、画面上に取り消しの導線はありません**（2026-09-06 実機確認）。有効化は社内の採用責任者の承認を得たうえで、登録済みの応募者を定期的に人が確認する運用とセットにしてください。

### 設定

```yaml
hrmos_evaluation:
  enabled: false        # true で有効化
  dry_run: true         # true: 登録の直前まで操作してログに出すだけ（登録しない）
  max_per_run: 20       # 1回の実行で登録する上限件数（設定ミス時の大量登録を防ぐ）
  max_age_days: 3       # 応募日時がこの日数以内の応募者だけを対象にする
  comment: "自動評価"   # 総合評価コメント欄に入れる文言
```

**初めて有効にするときは `dry_run: true` のまま1回実行**し、ログとメールに出る内訳が想定どおりかを確認してから `false` にしてください。`python run.py scan --dry-run` でも同じことができます（config が `false` でも登録しません）。

### 対象にならない応募者

| 状況 | 記録 | 再実行時 |
|---|---|---|
| 1次通過候補が「○」 | なし | 毎回判定 |
| 年齢を読めない／年齢帯の設定範囲外（判定不能） | なし | 毎回判定 |
| 応募日時が `max_age_days` より古い | `too_old` | スキップ |
| 「選考を評価」が押せない（既に誰かが評価済み・選考が締切） | `no_form` | スキップ |
| 登録できたか確認できなかった | `submit_uncertain` | **スキップ**（二重登録の防止） |

**年齢から判定できない応募者は登録しません。** 点数を見ずに落とさないための仕組みで、Excelでは「？」と表示されます。`first_pass_criteria` の年齢帯に隙間があるとここに落ちるため、`run.py doctor` が警告します。

`run.py scan --all`（全応募者の再評価）では登録を行いません。結果は `applicants.hrmos_eval_status` に記録され、実行ごとの内訳はログとメール本文に1行で出ます。

## タスクスケジューラ（自動実行）

`setup\setup_scheduler.bat` を実行すると、平日 12:30 と 17:30 に `run_scan.bat` を実行するタスクが登録されます。`setup\install.bat` の途中でも登録できます。実行ログは `data/logs/scan_YYYYMMDD_HHMMSS.log` に残ります。

- **管理者権限は不要**です（ログオン中の自分のユーザーとして実行されます）
- タスク名はフォルダ名を接尾辞に含みます（例: `HRMOS_AutoEval_1230_AGS_HRMOS_AUTO_EVAL`）。同じPCに複数フォルダで導入しても衝突しません
- **スリープ対策（`StartWhenAvailable` / `WakeToRun` / バッテリー条件）は登録時に自動で設定されます**。以前の `schtasks` 版と違い、再登録しても設定は失われません

### 登録

```powershell
setup\setup_scheduler.bat

# 解除
powershell -ExecutionPolicy Bypass -File setup\setup_scheduler.ps1 -Unregister
```

### 管理

```powershell
# 状態・前回実行結果・次回実行時刻の確認
Get-ScheduledTask -TaskName HRMOS_AutoEval_1230 | Get-ScheduledTaskInfo

# タスクの削除
schtasks /delete /tn "HRMOS_AutoEval_1230" /f
```

### PCがスリープする環境での設定

既定のままだと、実行時刻にPCがスリープ・電源オフの場合はその回がスキップされ、**ログもメール通知も残りません**（無音で1回分が失われる）。以下を設定しておくと、復帰後に自動実行されます。

```powershell
foreach ($n in 'HRMOS_AutoEval_1230','HRMOS_AutoEval_1730') {
    $t = Get-ScheduledTask -TaskName $n
    $s = $t.Settings
    $s.StartWhenAvailable = $true          # 逃した回を復帰後に実行する
    $s.WakeToRun = $true                   # 実行時刻にPCを起こす
    $s.DisallowStartIfOnBatteries = $false # バッテリー駆動でも実行する
    $s.StopIfGoingOnBatteries = $false     # 実行中に電源が外れても中断しない
    Set-ScheduledTask -TaskName $n -Settings $s
}
```

> **注意**:
>
> - `setup_scheduler.bat` は既存タスクを削除して作り直すため、**再実行すると上記の設定は失われます**。再登録したら設定し直してください。
> - `WakeToRun` はOS側のスリープ解除タイマーが有効な場合のみ機能します。`powercfg /query SCHEME_CURRENT SUB_SLEEP RTCWAKE` が `0x00000000` を返す環境では効きません（`StartWhenAvailable` による復帰後の実行は機能します）。

## 出力ファイル

| 種類              | 場所                                    | 説明                                   |
| ----------------- | --------------------------------------- | -------------------------------------- |
| レポート（Excel） | `data/reports/ai_evaluation_*.xlsx`   | AI評価結果（マトリクス形式、スタイル付き） |
| データベース      | `data/hrmos.db`                       | 評価履歴・応募者情報（SQLite）         |
| ダウンロード書類  | `data/downloads/<応募者ID>/`          | PDF/Word/Excel原本                     |
| 診断アーティファクト | `data/debug/*.png/.html` | 異常時の画面・HTML（原因切り分け用）。応募者0件は `applicant_list_empty_*`、自動NG登録の失敗は `ng_*`。**`ng_*` は応募者詳細ページをそのまま保存するため氏名・連絡先・経歴を含む。原因を確認したら削除すること**（自動削除はしない） |

## プロジェクト構成

```
AGS_HRMOS_AUTO_EVAL/
├── run.py                  # CLIエントリーポイント
├── run_scan.bat            # scan 実行（引数 scheduled で無人モード）
├── はじめにお読みください.txt  # 配布物の道しるべ（SETUP_GUIDE.html へ誘導）
├── setup/                  # 導入・配布に関するもの一式
│   ├── install.bat         # インストーラ起動用（ASCII・install.ps1 を呼ぶだけ）
│   ├── install.ps1         # インストーラ本体（Python導入〜設定〜自己診断）
│   ├── setup_scheduler.bat # 定期実行の登録（起動用）
│   ├── setup_scheduler.ps1 # 定期実行の登録本体（スリープ対策込み）
│   ├── build_dist.ps1      # 配布用zipの作成（機密除外・入れ忘れ検知・head付与）
│   ├── SETUP_GUIDE.html         # 導入手順書（配布zipに同梱）
│   ├── SETUP_GUIDE.ADVANCED.html # 設定変更ガイド（配布zipに同梱）
│   ├── OVERVIEW.html            # 機能とアーキテクチャの解説（配布zipに同梱）
│   ├── DISTRIBUTION.md          # 配る側の手順書（配布zipには含めない）
│   └── AGS_HRMOS_AUTO_EVAL_*.zip # 生成物（.gitignore 対象）
├── config.yaml.example     # 設定ファイルのテンプレート
├── requirements.txt        # Python依存パッケージ
├── ROADMAP.md              # 未対応タスク一覧
├── src/
│   ├── main.py             # メインオーケストレーター
│   ├── config.py           # 設定管理（YAML + 環境変数）
│   ├── doctor.py           # 環境自己診断（run.py doctor）
│   ├── browser/
│   │   ├── auth.py         # HRMOS認証（2段階ログイン・セッション有効性判定）
│   │   ├── navigator.py    # 応募者一覧巡回・ダウンロード（読み取りのみ）
│   │   ├── evaluation_form.py # 自動NG評価の登録（HRMOSへの書き込みはここだけ）
│   │   ├── page_utils.py   # ページ遷移の共通処理（リトライ付き）
│   │   └── selectors.py    # ページ要素のセレクタ定義
│   ├── parser/
│   │   └── document.py     # PDF/Word/Excelテキスト抽出
│   ├── evaluator/
│   │   ├── llm_client.py        # LLMプロバイダー切替（Claude/Gemini API/Gemini CLI）
│   │   ├── claude_client.py     # Claude CLI呼び出し（リトライ付き。プロジェクト外のフォルダで、会話保存なし・道具なしで起動）
│   │   ├── gemini_api_client.py # Gemini REST API呼び出し（APIキー認証・推奨）
│   │   ├── gemini_client.py     # Gemini CLI呼び出し（非推奨・個人アカウント提供終了）
│   │   ├── pii_masker.py        # LLM送信前の個人情報マスキング（氏名・電話・住所・メール・郵便番号・生年月日の月日）
│   │   ├── prompt_builder.py    # 評価プロンプト構築
│   │   └── response_parser.py   # JSON応答パース・検証
│   ├── database/
│   │   ├── models.py       # SQLiteスキーマ定義
│   │   └── repository.py   # データアクセス層
│   └── reporter/
│       ├── export.py       # Excel評価レポート出力
│       └── notify.py       # メール通知（Resend。評価できなかった応募者も表示）
├── tests/                  # 全91件。pytest は別途要インストール（requirements.txt に未収録）
│   ├── test_pii_masker.py  # PIIマスキングのユニットテスト
│   ├── test_first_pass.py  # 1次通過判定（○/△/×/判定不能）・応募日時パースのユニットテスト
│   ├── test_claude_client.py # Claude CLI の起動引数・起動フォルダ
│   └── test_notify.py      # 結果メールの「評価できなかった応募者」表示
├── improvement_list/       # 改修履歴（YYYY-MM-DD_{説明}.md）
├── docs/                   # 総括報告書・アーキテクチャ図
└── data/                   # 実行時に自動生成
    ├── downloads/
    ├── reports/
    ├── logs/               # 実行ログ（run_scan.bat 経由）
    ├── debug/              # 異常時の診断用スクショ・HTML
    └── hrmos.db
```

## 評価基準のカスタマイズ

`config.yaml` の `evaluation_criteria` セクションを編集して、自由に評価項目を追加・変更できます。

```yaml
evaluation_criteria:
  - name: "評価項目名"
    description: "AIに伝える評価の観点・基準の説明"
```

- 各項目は1〜5点でスコアリングされます
- `description` を具体的に書くほど評価精度が上がります
- 項目数に制限はありませんが、多すぎるとLLM CLIの処理時間が長くなります
- **評価基準を変えると過去の評価と比較できなくなります。** `config.yaml` は git 管理外で履歴が残らないため、変更したら `improvement_list/` に日付と変更内容を記録してください

### 使うモデルの固定

```yaml
evaluation:
  provider: "claude"
  model: "opus"     # claude なら sonnet / opus、gemini_api なら API のモデル名
```

**`model` は必ず書いてください。** 空にすると Claude CLI のその時点の既定モデル（＝開発者が Claude Code で選んでいるモデル）が使われ、そちらを切り替えた瞬間に応募者の採点基準も変わります。実際 2026-09-09 に既定モデルが CLI の対応外バージョンに変わり、評価が全件失敗する状態になりました。

モデルを変えると採点の傾向も変わります（実測で平均 0.07〜0.2 点の差）。変更後は過去の応募者を再評価して点差を確認してください。

### 1次通過の閾値

`first_pass_criteria` は年齢帯ごとの平均点しきい値です。**平均点は評価項目数で割った値なので、取りうる値は飛び飛びになります**（7項目なら 0.143 刻み）。そのため `3.9` と `4.0` のように、間に取りうる値がない2つの設定は同じ判定になります。閾値を変えるときは実際の点数分布を見て決めてください。

面接質問の観点も `interview_questions.perspective` で自由にカスタマイズできます。

## トラブルシューティング

### ログインに失敗する

- `config.yaml` のメールアドレス・パスワードが正しいか確認してください。
- HRMOS側でパスワード変更やアカウントロックが発生していないか確認してください。
- `headless: false` にしてブラウザ画面を見ながら原因を特定してください。

### AI評価が動かない

まず自己診断を実行してください。原因の切り分けが1コマンドで済みます。

```powershell
.venv\Scripts\python.exe run.py doctor
```

`AI評価の疎通` の行が `NG` の場合、プロバイダーごとに次を確認します。

**`gemini_api` の場合**

- 環境変数 `GEMINI_API_KEY` が設定されているか（設定後は新しいウィンドウで実行）
- キーが有効か・**課金が有効なプロジェクトのキーか**（[AI Studio](https://aistudio.google.com/apikey) で確認）
- `HTTP 400/403` が出る場合はキーの誤り・APIの制限設定・地域制限を確認

**`claude` の場合**

```powershell
claude --version   # 導入確認
claude doctor      # インストール診断
```

インストール済みでも**初回のブラウザ認証が済んでいないと非対話実行は失敗します**。一度 `claude` を起動してログインを完了してください。無人実行を安定させたい場合は `claude setup-token` で発行したトークンを環境変数 `CLAUDE_CODE_OAUTH_TOKEN` に設定します。

`API Error: 400 ... does not support this model` が出る場合は、**Claude CLI のバージョンが `config.yaml` の `evaluation.model` に対応していません**。`claude update` で CLI を更新するか、`model` を対応するモデル（`sonnet` など）に変更してください。

**`gemini`（CLI）の場合**

2026-06-18 に個人アカウント向けの提供が終了しています。`config.yaml` の `provider` を `gemini_api` に変更してください。

### AI評価がタイムアウトする

`config.yaml` の `evaluation.timeout` を増やしてください（デフォルト: 300秒）。

### Playwrightのインストールに失敗する

```bash
pip install playwright
playwright install chromium --with-deps
```

### セッション切れで途中停止する

`storage_state.json` を削除して再実行すると、新しいセッションでログインします。

```bash
del storage_state.json
python run.py scan
```

### 「応募者一覧の取得0件」の失敗アラートが届く

セッション失効途中（ログイン画面には飛ばないが一覧が空になる状態）が主な原因です。本ツールは一覧の描画有無まで確認して自動的に再ログインを試みるため、多くは次回実行で復旧します。再発・継続する場合は次を確認してください。

- `data/debug/applicant_list_empty_*.png/.html` に失敗時点の画面が保存されます。ログイン画面が写っていればセッション要因、一覧の構造が変わっていればHRMOSのUI変更（`src/browser/selectors.py` の見直しが必要）です。
- 手動で復旧する場合は `storage_state.json` を削除して再実行します。

### 定期実行された形跡がない（ログもメールも届かない）

`data/logs/` に該当時刻のログが**無い**場合、実行して失敗したのではなく**そもそも起動していません**。この場合はアプリ側のログもメール通知も一切残らないため、ログだけ見ると「何も起きていない」ように見えます。

```powershell
# タスクの前回実行時刻と結果を確認（0x800710E0 = 実行条件を満たさず拒否された）
Get-ScheduledTask -TaskName HRMOS_AutoEval_1730 | Get-ScheduledTaskInfo

# その時刻にPCが動いていたかを確認（42=スリープ開始 / 107=復帰）
Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-Power'; Id=42,107,506,507} -MaxEvents 20 |
    Select-Object TimeCreated, Id
```

PCのスリープが原因だった場合は、「タスクスケジューラ（自動実行）」の **PCがスリープする環境での設定** を適用してください。

## 改修履歴（improvement_list/）

`improvement_list/` ディレクトリに改修履歴を記録しています。

- ファイル名は `YYYY-MM-DD_{短い説明}.md` 形式（例: `2026-06-04_notify_no_candidates_and_failure.md`）
- 1プラン（計画単位）＝1ファイル。各ファイルに「対象・変更内容・理由」を記載し、履歴として残す
- 未完了のタスクがあれば「残作業」セクションに追記する
- 軽微な修正（誤字・フォーマット等）は記録不要
- 対応した機能については、必要に応じて本READMEへ反映する
