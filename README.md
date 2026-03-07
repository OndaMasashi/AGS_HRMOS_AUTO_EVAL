# HRMOS採用 応募者書類AI評価ツール

HRMOS採用ページをクローリングし、応募者一覧から履歴書等の書類（PDF/Word/Excel）を自動ダウンロードし、Claude AIが評価基準に基づいて各応募者を自動評価・スコアリングし、面接質問候補とともにExcelレポートを出力するCLIツールです。

## 主な機能

- 応募者書類の自動ダウンロード（PDF/Word/Excel対応）
- Claude CLI / Gemini CLIによるAI自動評価（設定した評価基準に基づく1〜5点のスコアリング、configで切替可能）
- 面接質問候補の自動生成（応募者ごとに3問）
- Excel一覧表の自動出力（レーダーチャート・1次通過候補・備考欄付き）
- メール通知（Resend API、オプション。1次通過候補・平均点を含むサマリ）
- 差分処理（未評価の応募者のみ自動処理）

## 動作環境

- **OS**: Windows 10/11
- **Python**: 3.10 以上
- **ブラウザ**: Chromium（Playwrightが自動インストール）
- **Claude CLI**: インストール済みであること（claude.aiライセンス使用）※デフォルト
- **Gemini CLI**: Geminiを使う場合（`npm install -g @google/gemini-cli`）※オプション

## セットアップ手順

### かんたんセットアップ（推奨）

配布された zip を任意の場所に展開し、`setup.bat` をダブルクリックするだけです。

1. zip を任意のフォルダに展開
2. `setup.bat` をダブルクリック（Python確認・仮想環境・依存パッケージ・Chromium を自動セットアップ）
3. `config.yaml` をテキストエディタで開き、HRMOSのログイン情報を入力
4. `run_scan.bat` をダブルクリックで実行

> **前提条件**:
> - Python 3.10 以上がインストール済みであること（未インストールの場合、setup.bat が案内を表示します）
> - Gemini CLI がインストール済みであること（`npm install -g @google/gemini-cli`）

### 手動セットアップ

setup.bat を使わずに手動でセットアップする場合は、以下の手順に従ってください。

#### 1. ソースコードの取得

配布された zip を任意の場所に展開します。

#### 2. Python仮想環境の作成・有効化

```bash
python -m venv .venv
.venv\Scripts\activate
```

#### 3. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

#### 4. Playwrightブラウザのインストール

```bash
playwright install chromium
```

#### 5. Gemini CLIの確認

デフォルトではGemini CLIを使用します。ターミナルから `gemini` コマンドが実行できることを確認してください。

```bash
gemini --version
```

未インストールの場合:

```bash
npm install -g @google/gemini-cli
```

Claude CLIを使用する場合は、`config.yaml` の `evaluation.provider` を `"claude"` に変更してください。

#### 6. 設定ファイルの作成

`config.yaml.example` をコピーして `config.yaml` を作成し、各項目を編集します。

```bash
copy config.yaml.example config.yaml
```

`config.yaml` を開いて以下を設定してください。

```yaml
# HRMOS採用のログイン情報
credentials:
  email: "your-email@example.com"
  password: "your-password"

# AI評価基準（項目名と説明を自由に追加・変更可）
evaluation_criteria:
  - name: "技術スキル"
    description: "プログラミング言語（Python, JavaScript等）、AI/ML、クラウド（AWS, GCP等）の技術経験と深さ"
  # ... 必要に応じて追加・変更
```

> **補足**: 認証情報・APIキーは環境変数でも指定できます。
>
> ```bash
> set HRMOS_EMAIL=your-email@example.com
> set HRMOS_PASSWORD=your-password
> set RESEND_API_KEY=re_xxxxx
> ```

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
| 1次通過候補 | 年齢帯×平均点閾値に基づく判定（○/△/空） |
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

AI評価が完了した場合、結果をメールで自動通知します。Excelレポートが添付され、本文には応募者ごとの合計点・総合評価のサマリが含まれます。

### セットアップ

1. [Resend](https://resend.com) でアカウントを作成し、APIキーを取得
2. `config.yaml` の `email` セクションを設定

### 動作条件

- `email.enabled: true` であること
- 評価済み応募者が1名以上いること（0名の場合はメール送信しません）

## タスクスケジューラ（自動実行）

Windowsタスクスケジューラで定期実行を設定できます。

### 登録コマンド例

```powershell
# 平日 12:00 に実行
schtasks /create /tn "HRMOS_Eval_Noon" /tr "\"C:\Users\<ユーザー名>\AppData\Local\Programs\Python\Python313\python.exe\" \"C:\work\AGS_HRMOS_AUTO_EVAL\run.py\" scan" /sc weekly /d MON,TUE,WED,THU,FRI /st 12:00

# 平日 17:00 に実行
schtasks /create /tn "HRMOS_Eval_Evening" /tr "\"C:\Users\<ユーザー名>\AppData\Local\Programs\Python\Python313\python.exe\" \"C:\work\AGS_HRMOS_AUTO_EVAL\run.py\" scan" /sc weekly /d MON,TUE,WED,THU,FRI /st 17:00
```

### 管理

```powershell
# タスク一覧の確認
schtasks /query /tn HRMOS_Eval_Noon

# タスクの削除
schtasks /delete /tn "HRMOS_Eval_Noon" /f
```

> **注意**: PCがログオン状態でないとタスクは実行されません（Interactive onlyモード）。

## 出力ファイル

| 種類              | 場所                                    | 説明                                   |
| ----------------- | --------------------------------------- | -------------------------------------- |
| レポート（Excel） | `data/reports/ai_evaluation_*.xlsx`   | AI評価結果（マトリクス形式、スタイル付き） |
| データベース      | `data/hrmos.db`                       | 評価履歴・応募者情報（SQLite）         |
| ダウンロード書類  | `data/downloads/<応募者ID>/`          | PDF/Word/Excel原本                     |

## プロジェクト構成

```
AGS_HRMOS_AUTO_EVAL/
├── run.py                  # CLIエントリーポイント
├── config.yaml.example     # 設定ファイルのテンプレート
├── requirements.txt        # Python依存パッケージ
├── src/
│   ├── main.py             # メインオーケストレーター
│   ├── config.py           # 設定管理（YAML + 環境変数）
│   ├── browser/
│   │   ├── auth.py         # HRMOS認証（2段階ログイン）
│   │   ├── navigator.py    # 応募者一覧巡回・ダウンロード
│   │   └── selectors.py    # ページ要素のセレクタ定義
│   ├── parser/
│   │   └── document.py     # PDF/Word/Excelテキスト抽出
│   ├── evaluator/
│   │   ├── llm_client.py        # LLMプロバイダー切替（Claude/Gemini）
│   │   ├── claude_client.py     # Claude CLI呼び出し（リトライ付き）
│   │   ├── gemini_client.py     # Gemini CLI呼び出し（リトライ付き）
│   │   ├── prompt_builder.py    # 評価プロンプト構築
│   │   └── response_parser.py   # JSON応答パース・検証
│   ├── database/
│   │   ├── models.py       # SQLiteスキーマ定義
│   │   └── repository.py   # データアクセス層
│   └── reporter/
│       ├── export.py       # Excel評価レポート出力
│       └── notify.py       # メール通知（Resend）
└── data/                   # 実行時に自動生成
    ├── downloads/
    ├── reports/
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

面接質問の観点も `interview_questions.perspective` で自由にカスタマイズできます。

## トラブルシューティング

### ログインに失敗する

- `config.yaml` のメールアドレス・パスワードが正しいか確認してください。
- HRMOS側でパスワード変更やアカウントロックが発生していないか確認してください。
- `headless: false` にしてブラウザ画面を見ながら原因を特定してください。

### LLM CLIが見つからない

```bash
# Claudeの場合
claude --version

# Geminiの場合
gemini --version
```

使用するプロバイダーのCLIがインストール済みか確認してください。Geminiの場合は `npm install -g @google/gemini-cli` でインストールできます。

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

## 改修課題管理（improvement_list/）

`improvement_list/` ディレクトリに改修課題を管理しています。

- 日付ベースのファイル（例: `20260225.md`）に課題を箇条書きで記載
- 課題の対応が完了したら、ファイルごと削除する
- 対応した機能については、必要に応じて本READMEへ反映する
