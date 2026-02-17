下記HRMOS採用ページに掲載の応募者について、それぞれの応募者の個別ページに遷移し、そこに添付されている履歴書や経歴書を参照し、特定の文言（「AI」など）が含まれていたらピックアップして検知する仕組みを構築したい。定期的に実施するので、どこまで検知完了したかどうかは履歴として残せるようにしたい。可能か？可能であればプランを作成してほしい。
https://hrmos.co/interviews



# HRMOS採用 応募者書類キーワード検知システム

## Context

HRMOS採用（hrmos.co/interviews）に掲載されている応募者の履歴書・経歴書に特定のキーワード（「AI」「機械学習」等）が含まれているかを自動検知したい。定期的に実行し、どこまで検知完了したかの履歴を残す必要がある。

HRMOS採用には公開APIが存在しないため、**Playwrightによるブラウザ自動操作**で応募者ページを巡回し、添付ファイルをダウンロード・解析するアプローチを採る。

## 技術スタック

| 用途             | 技術                   |
| ---------------- | ---------------------- |
| ブラウザ自動操作 | Python + Playwright    |
| PDF解析          | pdfplumber             |
| Word解析         | python-docx            |
| Excel解析        | openpyxl               |
| 履歴管理         | SQLite                 |
| 設定管理         | YAML (config.yaml)     |
| 結果出力         | CSV / openpyxl (Excel) |

## プロジェクト構成

```
c:\work\AGS_HRMOS_RETRIEVE\
├── config.yaml              # 設定ファイル（キーワード、URL等）
├── config.yaml.example      # 設定ファイルのテンプレート
├── requirements.txt         # Python依存パッケージ
├── run.py                   # エントリーポイント（CLIコマンド）
├── src/
│   ├── __init__.py
│   ├── browser/
│   │   ├── __init__.py
│   │   ├── auth.py          # HRMOS認証（メール+パスワード、セッション再利用）
│   │   ├── navigator.py     # 応募者一覧・個別ページ巡回
│   │   ├── downloader.py    # 添付ファイルダウンロード
│   │   └── selectors.py     # CSSセレクタ一元管理
│   ├── parser/
│   │   ├── __init__.py
│   │   └── document.py      # PDF/Word/Excel文書のテキスト抽出
│   ├── scanner/
│   │   ├── __init__.py
│   │   └── keyword.py       # キーワード検索ロジック
│   ├── database/
│   │   ├── __init__.py
│   │   ├── models.py        # SQLiteスキーマ定義
│   │   └── repository.py    # データアクセス層（履歴CRUD）
│   └── reporter/
│       ├── __init__.py
│       └── export.py         # CSV/Excel結果出力
├── data/
│   ├── downloads/            # ダウンロードした添付ファイル（一時保存）
│   ├── reports/              # 出力レポート（CSV/Excel）
│   └── hrmos.db              # SQLiteデータベース
└── storage_state.json        # Playwrightセッション保存（.gitignore対象）
```

## 実装ステップ

### Step 1: プロジェクト初期化

* `requirements.txt` 作成（playwright, pdfplumber, python-docx, openpyxl, pyyaml）
* `config.yaml.example` 作成
* ディレクトリ構造作成

### Step 2: 設定管理 (`config.yaml`)

```yaml
hrmos:
  base_url: "https://hrmos.co/interviews"
  login_url: "https://hrmos.co/login"  # 要確認

credentials:
  email: ""       # 環境変数 HRMOS_EMAIL でも指定可
  password: ""    # 環境変数 HRMOS_PASSWORD でも指定可

keywords:
  - "AI"
  - "機械学習"
  - "Python"
  # 追加キーワードはここに列挙

scan:
  download_dir: "./data/downloads"
  report_dir: "./data/reports"
  db_path: "./data/hrmos.db"
  wait_between_pages: 2  # ページ間の待機秒数（サーバー負荷軽減）
```

### Step 3: データベース設計 (`models.py`)

```sql
-- 応募者テーブル
CREATE TABLE applicants (
    id TEXT PRIMARY KEY,          -- HRMOS上の応募者ID or ページURL
    name TEXT,                    -- 応募者名
    page_url TEXT,                -- 個別ページURL
    status TEXT DEFAULT 'pending', -- pending / scanned / error
    scanned_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 添付ファイルテーブル
CREATE TABLE documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    applicant_id TEXT REFERENCES applicants(id),
    filename TEXT,
    file_type TEXT,               -- pdf / docx / xlsx
    file_path TEXT,
    parsed_text_length INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- キーワードマッチテーブル
CREATE TABLE keyword_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    applicant_id TEXT REFERENCES applicants(id),
    document_id INTEGER REFERENCES documents(id),
    keyword TEXT,
    context TEXT,                  -- マッチ箇所の前後テキスト
    scan_run_id TEXT,              -- 実行バッチID
    found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 実行履歴テーブル
CREATE TABLE scan_runs (
    id TEXT PRIMARY KEY,           -- UUID
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    total_applicants INTEGER,
    scanned_count INTEGER,
    match_count INTEGER,
    status TEXT                    -- running / completed / failed
);
```

### Step 4: 認証モジュール (`auth.py`)

* メール+パスワードでログイン
* `storage_state.json` にセッション保存し、次回起動時に再利用
* セッション切れの場合は自動で再ログイン

### Step 5: ページ巡回モジュール (`navigator.py`)

* 応募者一覧ページを開く
* ページネーション対応（次ページへの遷移）
* 各応募者のリンクを収集
* 個別ページへ遷移し、添付ファイルのリンクを取得
* **注意** : CSSセレクタは `selectors.py` に集約し、HRMOS UI変更時に1箇所だけ修正すればよい設計

### Step 6: ファイルダウンロード (`downloader.py`)

* Playwrightのダウンロードイベントを利用
* `data/downloads/{applicant_id}/` 配下にファイル保存
* ダウンロード済みファイルはスキップ

### Step 7: 文書解析 (`document.py`)

* **PDF** : `pdfplumber` でテキスト抽出
* **Word (.docx)** : `python-docx` でテキスト抽出
* **Excel (.xlsx)** : `openpyxl` で全シート・全セルのテキスト抽出
* 抽出失敗時はエラーログを記録し、次の応募者に進む

### Step 8: キーワード検索 (`keyword.py`)

* 抽出テキストに対し設定されたキーワードを検索
* 大文字/小文字を区別しない検索
* マッチした場合、前後の文脈（50文字程度）も記録
* 結果をDBに保存

### Step 9: レポート出力 (`export.py`)

* CSV/Excelファイルに以下を出力:
  * 応募者名、ページURL、マッチしたキーワード、文脈、ファイル名、検知日時
* 実行ごとにタイムスタンプ付きファイル名で保存

### Step 10: CLIエントリーポイント (`run.py`)

```
python run.py scan          # フルスキャン（未スキャンの応募者のみ）
python run.py scan --all    # 全応募者を再スキャン
python run.py report        # 最新の結果をCSV/Excel出力
python run.py status        # スキャン進捗状況の表示
```

## セレクタ発見について（重要）

HRMOS採用のページ構造（CSSセレクタ）は事前に把握できないため、以下の手順で初回セットアップが必要:

1. `playwright codegen https://hrmos.co` を実行
2. 手動でログイン → 応募者一覧 → 個別ページを操作
3. 記録されたセレクタを `selectors.py` に転記
4. 必要に応じてセレクタを調整

## セキュリティ考慮事項

* 認証情報は `config.yaml` または環境変数（`HRMOS_EMAIL`, `HRMOS_PASSWORD`）で管理
* `config.yaml`, `storage_state.json`, `data/` は `.gitignore` に追加
* ダウンロードした履歴書は処理後に削除するオプションを提供

## 検証方法

1. `pip install -r requirements.txt && playwright install chromium` で環境構築
2. `config.yaml` に認証情報とキーワードを設定
3. `playwright codegen` でセレクタを発見・設定
4. `python run.py scan` でスキャン実行
5. `python run.py report` で結果確認
6. `python run.py status` で履歴確認
7. 2回目の `python run.py scan` で既スキャン応募者がスキップされることを確認



## 実装完了

以下のファイルを作成しました:

| ファイル                                                                                                                    | 役割                                                                 |
| --------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| [run.py](vscode-webview://06n118f4qrp3uatqrg4i1agnfphosbtu0hl893kb5m1j3k45n94f/run.py)                                         | CLIエントリーポイント（`scan` / `report` / `status` コマンド） |
| [config.yaml.example](vscode-webview://06n118f4qrp3uatqrg4i1agnfphosbtu0hl893kb5m1j3k45n94f/config.yaml.example)               | 設定ファイルのテンプレート                                           |
| [requirements.txt](vscode-webview://06n118f4qrp3uatqrg4i1agnfphosbtu0hl893kb5m1j3k45n94f/requirements.txt)                     | Python依存パッケージ                                                 |
| [src/config.py](vscode-webview://06n118f4qrp3uatqrg4i1agnfphosbtu0hl893kb5m1j3k45n94f/src/config.py)                           | 設定管理（YAML + 環境変数フォールバック）                            |
| [src/main.py](vscode-webview://06n118f4qrp3uatqrg4i1agnfphosbtu0hl893kb5m1j3k45n94f/src/main.py)                               | メインオーケストレーター（全体制御）                                 |
| [src/browser/auth.py](vscode-webview://06n118f4qrp3uatqrg4i1agnfphosbtu0hl893kb5m1j3k45n94f/src/browser/auth.py)               | HRMOS認証（メール+パスワード、セッション保存）                       |
| [src/browser/selectors.py](vscode-webview://06n118f4qrp3uatqrg4i1agnfphosbtu0hl893kb5m1j3k45n94f/src/browser/selectors.py)     | CSSセレクタ一元管理                                                  |
| [src/browser/navigator.py](vscode-webview://06n118f4qrp3uatqrg4i1agnfphosbtu0hl893kb5m1j3k45n94f/src/browser/navigator.py)     | 応募者一覧・個別ページ巡回                                           |
| [src/browser/downloader.py](vscode-webview://06n118f4qrp3uatqrg4i1agnfphosbtu0hl893kb5m1j3k45n94f/src/browser/downloader.py)   | 添付ファイルダウンロード                                             |
| [src/parser/document.py](vscode-webview://06n118f4qrp3uatqrg4i1agnfphosbtu0hl893kb5m1j3k45n94f/src/parser/document.py)         | PDF/Word/Excelテキスト抽出                                           |
| [src/scanner/keyword.py](vscode-webview://06n118f4qrp3uatqrg4i1agnfphosbtu0hl893kb5m1j3k45n94f/src/scanner/keyword.py)         | キーワード検索（大文字小文字無視、文脈付き）                         |
| [src/database/models.py](vscode-webview://06n118f4qrp3uatqrg4i1agnfphosbtu0hl893kb5m1j3k45n94f/src/database/models.py)         | SQLiteスキーマ定義                                                   |
| [src/database/repository.py](vscode-webview://06n118f4qrp3uatqrg4i1agnfphosbtu0hl893kb5m1j3k45n94f/src/database/repository.py) | データアクセス層（履歴・進捗管理）                                   |
| [src/reporter/export.py](vscode-webview://06n118f4qrp3uatqrg4i1agnfphosbtu0hl893kb5m1j3k45n94f/src/reporter/export.py)         | CSV/Excelレポート出力                                                |

## 使い方

### 1. 環境構築

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 設定ファイル作成

```bash
copy config.yaml.example config.yaml
# config.yaml にメールアドレス・パスワード・キーワードを設定
```

### 3. セレクタの発見（初回のみ）

```bash
playwright codegen https://hrmos.co
```

ブラウザが開くので、手動でログイン → 応募者一覧 → 個別ページを操作し、記録されたセレクタを [src/browser/selectors.py](vscode-webview://06n118f4qrp3uatqrg4i1agnfphosbtu0hl893kb5m1j3k45n94f/src/browser/selectors.py) に転記してください。

### 4. 実行

```bash
python run.py scan          # 未スキャンの応募者のみスキャン
python run.py scan --all    # 全応募者を再スキャン
python run.py report        # 結果をCSV/Excelに出力
python run.py status        # スキャン進捗を確認
```

 **重要** : [selectors.py](vscode-webview://06n118f4qrp3uatqrg4i1agnfphosbtu0hl893kb5m1j3k45n94f/src/browser/selectors.py) の `TODO` コメント箇所は、実際のHRMOS UIに合わせて `playwright codegen` の結果で更新する必要があります。これが動作させるための最も重要なステップです。
