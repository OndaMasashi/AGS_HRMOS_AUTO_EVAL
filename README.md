# HRMOS採用 応募者書類キーワード検知ツール

HRMOS採用ページをクローリングし、応募者一覧から履歴書等の書類（PDF/Word/Excel）を自動ダウンロードし、書類内から指定キーワードを検索してレポート出力するCLIツールです。

## 動作環境

- **OS**: Windows 10/11
- **Python**: 3.10 以上
- **ブラウザ**: Chromium（Playwrightが自動インストール）

## セットアップ手順

### 1. ソースコードの取得

配布された `AGS_HRMOS_RETRIEVE_dist.zip` を任意の場所に展開します。

```powershell
# 例: C:\work に展開する場合
Expand-Archive -Path AGS_HRMOS_RETRIEVE_dist.zip -DestinationPath C:\work
```

PowerShellで展開先に移動します。

```powershell
cd C:\work\AGS_HRMOS_RETRIEVE   # 展開したパスに合わせて変更
```

### 2. Python仮想環境の作成・有効化

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 3. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 4. Playwrightブラウザのインストール

```bash
playwright install chromium
```

### 5. 設定ファイルの作成

`config.yaml.example` をコピーして `config.yaml` を作成し、**認証情報**と**キーワード**を編集します。

```bash
copy config.yaml.example config.yaml
```

`config.yaml` を開いて以下を設定してください。

```yaml
hrmos:
  base_url: "https://hrmos.co/interviews"
  login_url: "https://hrmos.co/login"

# HRMOS採用のログイン情報
credentials:
  email: "your-email@example.com"
  password: "your-password"

# 検索したいキーワード（大文字/小文字を区別しない）
keywords:
  - "AI"
  - "機械学習"
  - "Python"

scan:
  download_dir: "./data/downloads"   # ダウンロード先
  report_dir: "./data/reports"       # レポート出力先
  db_path: "./data/hrmos.db"         # SQLiteデータベース
  wait_between_pages: 2              # ページ間の待機秒数
  headless: false                    # true: ブラウザ非表示 / false: ブラウザ表示
  delete_downloads_after: false      # true: 解析後にダウンロードファイルを削除

# メール通知設定（Resend）
email:
  enabled: true                          # true: スキャン後にメール送信 / false: 無効
  api_key: "re_xxxxx"                    # Resend APIキー
  from: "onboarding@resend.dev"          # 送信元（独自ドメイン設定後に変更）
  to:
    - "your-email@example.com"           # 送信先（複数指定可）
  subject_prefix: "[HRMOS]"              # 件名のプレフィックス
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

**日々の実行はこのコマンドだけでOKです。** スキャン → レポート出力まで自動で行われます。

```powershell
python run.py scan
```

前回スキャン済みの応募者は自動的にスキップされるため、**新規・未処理の応募者のみ**が対象になります。レポートにもその回の差分のみが出力されます。

### コマンド一覧

| コマンド                               | 説明                                       | 用途                         |
| -------------------------------------- | ------------------------------------------ | ---------------------------- |
| `python run.py scan`                 | スキャン実行＋レポート自動出力             | **日常はこれだけ実行** |
| `python run.py scan --all`           | 全応募者を再スキャン（スキャン済みも含む） | キーワード追加時など         |
| `python run.py report`               | DB内の過去全件のマッチ結果をレポート出力   | 過去データの再出力           |
| `python run.py report --run-id <ID>` | 特定回のマッチ結果のみレポート出力         | 特定回の結果だけ欲しいとき   |
| `python run.py status`               | スキャン進捗状況を表示                     | 処理状況の確認               |

> **scan と report の違い**: `scan` はスキャン実行後にその回のマッチ結果を自動でCSV/Excelに出力します。`report` はスキャンは行わず、DBに蓄積された過去の結果をまとめて再出力するためのコマンドです。

### オプション

各コマンドに `-v` を付けるとデバッグログが出力されます。

```powershell
python run.py -v scan
```

## メール通知（Resend）- オプション

> **この機能は任意です。** 設定しなくてもスキャン・レポート出力は通常通り動作します。メール通知が不要な場合は `email.enabled: false`（デフォルト）のままで問題ありません。

スキャンでキーワードマッチが見つかった場合、結果をメールで自動通知します。Excelレポートが添付され、本文にはマッチ一覧のサマリーが含まれます。

### セットアップ

1. [Resend](https://resend.com) でアカウントを作成し、APIキーを取得
2. `config.yaml` の `email` セクションを設定

```yaml
email:
  enabled: true
  api_key: "re_xxxxx"
  from: "onboarding@resend.dev"
  to:
    - "your-email@example.com"
  subject_prefix: "[HRMOS]"
```

> **注意**: テスト用送信元 `onboarding@resend.dev` はResendアカウントに登録したメールアドレスにのみ送信可能です。他の宛先にも送る場合はResendで独自ドメインを認証してください。

### 動作条件

- `email.enabled: true` であること
- スキャン結果のマッチが1件以上あること（0件の場合はメール送信しません）

## タスクスケジューラ（自動実行）

Windowsタスクスケジューラで定期実行を設定できます。

### 登録コマンド例

```powershell
# 平日 12:00 に実行
schtasks /create /tn "HRMOS_Scan_Noon" /tr "\"C:\Users\<ユーザー名>\AppData\Local\Programs\Python\Python313\python.exe\" \"C:\work\AGS_HRMOS_RETRIEVE\run.py\" scan" /sc weekly /d MON,TUE,WED,THU,FRI /st 12:00

# 平日 17:00 に実行
schtasks /create /tn "HRMOS_Scan_Evening" /tr "\"C:\Users\<ユーザー名>\AppData\Local\Programs\Python\Python313\python.exe\" \"C:\work\AGS_HRMOS_RETRIEVE\run.py\" scan" /sc weekly /d MON,TUE,WED,THU,FRI /st 17:00
```

### 管理

```powershell
# タスク一覧の確認
schtasks /query /tn HRMOS_Scan_Noon
schtasks /query /tn HRMOS_Scan_Evening

# タスクの削除
schtasks /delete /tn "HRMOS_Scan_Noon" /f
schtasks /delete /tn "HRMOS_Scan_Evening" /f
```

> **注意**: PCがログオン状態でないとタスクは実行されません（Interactive onlyモード）。タスクスケジューラのGUIからも確認・編集が可能です。

## 出力ファイル

| 種類              | 場所                                    | 説明                                 |
| ----------------- | --------------------------------------- | ------------------------------------ |
| レポート（CSV）   | `data/reports/keyword_matches_*.csv`  | キーワードマッチ結果                 |
| レポート（Excel） | `data/reports/keyword_matches_*.xlsx` | キーワードマッチ結果（スタイル付き） |
| データベース      | `data/hrmos.db`                       | スキャン履歴・応募者情報（SQLite）   |
| ダウンロード書類  | `data/downloads/<応募者ID>/`          | PDF/Word/Excel原本                   |

## プロジェクト構成

```
AGS_HRMOS_RETRIEVE/
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
│   ├── scanner/
│   │   └── keyword.py      # キーワード検索エンジン
│   ├── database/
│   │   ├── models.py       # SQLiteスキーマ定義
│   │   └── repository.py   # データアクセス層
│   └── reporter/
│       ├── export.py       # CSV/Excelレポート出力
│       └── notify.py       # メール通知（Resend）
└── data/                   # 実行時に自動生成
    ├── downloads/
    ├── reports/
    └── hrmos.db
```

## トラブルシューティング

### ログインに失敗する

- `config.yaml` のメールアドレス・パスワードが正しいか確認してください。
- HRMOS側でパスワード変更やアカウントロックが発生していないか確認してください。
- `headless: false` にしてブラウザ画面を見ながら原因を特定してください。

### Playwrightのインストールに失敗する

```bash
pip install playwright
playwright install chromium --with-deps
```

`--with-deps` を付けるとOS依存のライブラリも自動インストールされます。

### セッション切れで途中停止する

`storage_state.json` を削除して再実行すると、新しいセッションでログインします。

```bash
del storage_state.json
python run.py scan
```
