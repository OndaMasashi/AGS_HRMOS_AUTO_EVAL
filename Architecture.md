# Architecture - HRMOS 応募者書類 AI自動評価ツール

## 1. システム概要

HRMOS採用ページから応募者の書類（PDF/Word/Excel）を自動取得し、Claude AIで評価基準に基づくスコアリング・面接質問生成を行い、結果をExcel一覧表にまとめるCLIツール。

### 技術スタック

| 項目 | 技術 |
|------|------|
| 言語 | Python 3.10+ |
| ブラウザ自動化 | Playwright (Chromium) |
| AI評価 | Claude CLI (`claude -p`) via subprocess ※後述 |
| 書類パーサー | pdfplumber / python-docx / openpyxl |
| データベース | SQLite |
| Excel出力 | openpyxl |
| メール通知 | Resend API |
| 設定管理 | YAML + 環境変数 |

### Claude CLI によるAI評価の仕組み

本ツールは **Claude CLI（Claude Code）** の `claude -p`（パイプモード）をsubprocessで呼び出してAI評価を行う。APIキーは不要で、マシン上のCLI がログイン済みの **claude.ai アカウント**（Pro / Max プラン等）の認証情報をそのまま利用する。

```
Python subprocess
  └─▶ claude -p (stdin にプロンプト送信)
        └─▶ claude.ai (ログイン済みアカウントで推論)
              └─▶ stdout にテキスト応答を返却
```

- **APIキー不要**: CLIのログイン状態に依存（`claude` コマンドが使えれば動作）
- **応答形式**: プレーンテキスト（JSONを指示しているが保証はないため、パーサーで吸収）
- **前提条件**: `claude --version` が実行できること

---

## 2. ディレクトリ構成

```
AGS_HRMOS_AUTO_EVAL/
├── run.py                          # CLIエントリーポイント (argparse)
├── config.yaml                     # 設定ファイル（認証・評価基準・通知等）
├── config.yaml.example             # 設定テンプレート
├── requirements.txt                # 依存パッケージ
├── storage_state.json              # Playwrightセッション保存（自動生成）
│
├── src/
│   ├── main.py                     # メインオーケストレーター
│   ├── config.py                   # 設定読み込み・バリデーション
│   │
│   ├── browser/                    # [Layer] ブラウザ自動化
│   │   ├── auth.py                 #   HRMOS認証（2段階ログイン）
│   │   ├── navigator.py            #   応募者一覧巡回・添付DL
│   │   └── selectors.py            #   ページ要素セレクタ定義
│   │
│   ├── parser/                     # [Layer] 書類テキスト抽出
│   │   └── document.py             #   PDF / DOCX / XLSX → テキスト
│   │
│   ├── evaluator/                  # [Layer] AI評価
│   │   ├── claude_client.py        #   Claude CLI subprocess呼び出し
│   │   ├── prompt_builder.py       #   評価プロンプト構築 + ランク算出
│   │   └── response_parser.py      #   JSON応答パース・検証
│   │
│   ├── database/                   # [Layer] データ永続化
│   │   ├── models.py               #   SQLiteスキーマ定義・初期化
│   │   └── repository.py           #   CRUD操作
│   │
│   └── reporter/                   # [Layer] 出力・通知
│       ├── export.py               #   Excel評価レポート生成
│       └── notify.py               #   Resendメール通知
│
└── data/                           # 実行時に自動生成
    ├── downloads/{applicant_id}/   # ダウンロードした書類
    ├── reports/ai_evaluation_*.xlsx # 評価レポート
    └── hrmos.db                    # SQLiteデータベース
```

---

## 3. データフロー図 (DFD)

### Level 0 - コンテキスト図

```
                    ┌─────────────┐
   config.yaml ───▶ │             │ ──▶ Excel レポート
                    │   HRMOS     │
   HRMOS 採用  ◀──▶ │  AI自動評価  │ ──▶ メール通知
   (Webサイト)      │   ツール     │
                    │             │
   Claude CLI  ◀──▶ │             │ ──▶ SQLite DB
                    └─────────────┘
```

### Level 1 - 主要プロセス

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          python run.py scan                             │
│                                                                         │
│  ┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐           │
│  │  1.認証  │───▶│ 2.応募者 │───▶│ 3.書類   │───▶│ 4.テキスト│           │
│  │         │    │  一覧収集 │    │  ダウンロード│   │  抽出    │           │
│  └─────────┘    └──────────┘    └──────────┘    └────┬─────┘           │
│       │              │               │                │                 │
│    HRMOS          HRMOS           HRMOS          PDF/DOCX/XLSX          │
│   ログイン       一覧ページ       個別ページ        ファイル             │
│                      │                                │                 │
│                      ▼                                ▼                 │
│                 ┌──────────┐                    ┌──────────┐           │
│                 │  SQLite  │◀───────────────────│ 5.AI評価  │           │
│                 │  DB      │    評価結果格納     │          │           │
│                 │          │                    │ Claude CLI│           │
│                 └────┬─────┘                    └──────────┘           │
│                      │                                                  │
│              ┌───────┴────────┐                                         │
│              ▼                ▼                                         │
│        ┌──────────┐    ┌──────────┐                                    │
│        │ 6.Excel  │    │ 7.メール │                                    │
│        │  レポート │    │  通知    │                                    │
│        └──────────┘    └──────────┘                                    │
│              │                │                                         │
│              ▼                ▼                                         │
│         .xlsx ファイル    Resend API                                    │
└──────────────────────────────────────────────────────────────────────────┘
```

### Level 2 - AI評価プロセス詳細

```
                     応募者の全書類テキスト（結合済み）
                                │
                                ▼
┌─────────────────────────────────────────────────────────┐
│               prompt_builder.py                          │
│                                                          │
│  ┌────────────┐   ┌──────────────┐   ┌───────────────┐  │
│  │ 評価基準    │ + │ スコアリング  │ + │ 面接質問の    │  │
│  │ (config)   │   │ ルーブリック  │   │ 観点(config)  │  │
│  └────────────┘   └──────────────┘   └───────────────┘  │
│                         │                                │
│                         ▼                                │
│              JSON出力スキーマ付きプロンプト                │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│               claude_client.py                           │
│                                                          │
│   subprocess.run(["claude", "-p"], input=prompt)         │
│   ・stdin でプロンプト送信（引数長制限回避）               │
│   ・リトライ: 最大3回、間隔5秒                            │
│   ・タイムアウト: 120秒                                   │
│   ・テキスト切り詰め: 80,000文字                          │
└─────────────────────────┬───────────────────────────────┘
                          │ JSON文字列
                          ▼
┌─────────────────────────────────────────────────────────┐
│               response_parser.py                         │
│                                                          │
│   ・```json``` ラップの除去                               │
│   ・波括弧マッチングによるJSON抽出                         │
│   ・スコア値の整数正規化（1-5にクランプ）                  │
│   ・total_score 未返却時は自動計算                        │
│   ・gender / age のバリデーション                         │
└─────────────────────────┬───────────────────────────────┘
                          │ dict
                          ▼
                ┌───────────────────┐
                │ repository.py     │
                │ evaluationsテーブル│
                │ に一括INSERT       │
                └───────────────────┘
```

---

## 4. データベーススキーマ (ER図)

```
┌─────────────────────┐       ┌─────────────────────────┐
│     applicants      │       │       documents          │
├─────────────────────┤       ├─────────────────────────┤
│ id (PK)        TEXT │──┐    │ id (PK)     INTEGER     │
│ name           TEXT │  │    │ applicant_id TEXT (FK)───┤──┐
│ page_url       TEXT │  │    │ filename     TEXT        │  │
│ status         TEXT │  │    │ file_type    TEXT        │  │
│ scanned_at TIMESTAMP│  │    │ file_path    TEXT        │  │
│ created_at TIMESTAMP│  │    │ parsed_text_length INT   │  │
└─────────────────────┘  │    │ created_at   TIMESTAMP  │  │
                         │    └─────────────────────────┘  │
       ┌─────────────────┘                                 │
       │    ┌──────────────────────────────────────────────┘
       │    │
       ▼    ▼
┌──────────────────────────────┐      ┌──────────────────────┐
│        evaluations           │      │      scan_runs       │
├──────────────────────────────┤      ├──────────────────────┤
│ id (PK)         INTEGER      │      │ id (PK)     TEXT     │
│ applicant_id    TEXT (FK) ───┤      │ started_at  TIMESTAMP│
│ document_id     INTEGER (FK) │      │ completed_at TIMESTAMP│
│ criteria_name   TEXT         │      │ total_applicants INT │
│ score           INTEGER      │      │ scanned_count  INT   │
│ comment         TEXT         │      │ match_count    INT   │
│ total_score     INTEGER      │      │ status         TEXT  │
│ overall_comment TEXT         │      └──────────────────────┘
│ interview_questions TEXT     │
│ applicant_gender TEXT        │
│ applicant_age    INTEGER     │
│ scan_run_id     TEXT         │
│ raw_response    TEXT         │
│ evaluated_at    TIMESTAMP    │
└──────────────────────────────┘

※ evaluations は1応募者あたり評価基準の数だけ行が入る
  （例: 7基準 → 7行。total_score等の共通情報は各行に重複格納）
```

### status 遷移図 (applicants)

```
  ┌─────────┐     mark_applicant_scanned()    ┌──────────┐
  │ pending │ ───────────────────────────────▶ │ scanned  │
  └─────────┘                                  └──────────┘
       │                                            ▲
       │         mark_applicant_error()             │
       ├──────────────────────────┐                 │
       │                          ▼                 │
       │                    ┌──────────┐            │
       │                    │  error   │            │
       │                    └──────────┘            │
       │                                            │
       └────────── reset (--all フラグ) ────────────┘
```

---

## 5. 処理シーケンス (`python run.py scan`)

```
run.py          main.py         browser/        parser/         evaluator/      database/       reporter/
  │                │               │               │               │               │               │
  │──scan─────────▶│               │               │               │               │               │
  │                │──load_config──▶               │               │               │               │
  │                │──init_db──────────────────────────────────────────────────────▶│               │
  │                │──create_scan_run──────────────────────────────────────────────▶│               │
  │                │               │               │               │               │               │
  │                │──ensure_authenticated────────▶│               │               │               │
  │                │               │◀──success──── │               │               │               │
  │                │               │               │               │               │               │
  │                │──collect_applicant_links─────▶│               │               │               │
  │                │               │◀──[{id,name,url}]──          │               │               │
  │                │──upsert_applicant─────────────────────────────────────────────▶│               │
  │                │               │               │               │               │               │
  │                │  ┌── for each pending applicant ──────────────────────────────────────────┐   │
  │                │  │            │               │               │               │           │   │
  │                │  │──get_attachment_links─────▶│               │               │           │   │
  │                │  │──download_attachment──────▶│               │               │           │   │
  │                │  │            │               │               │               │           │   │
  │                │  │──extract_text──────────────────────────────▶               │           │   │
  │                │  │            │               │◀──text────── │               │           │   │
  │                │  │            │               │               │               │           │   │
  │                │  │──build_evaluation_prompt───────────────────▶               │           │   │
  │                │  │──call_claude───────────────────────────────▶               │           │   │
  │                │  │            │               │               │◀──JSON──────  │           │   │
  │                │  │──parse_evaluation_response─────────────────▶               │           │   │
  │                │  │            │               │               │◀──dict──────  │           │   │
  │                │  │            │               │               │               │           │   │
  │                │  │──add_evaluations_batch──────────────────────────────────────▶           │   │
  │                │  │──mark_applicant_scanned─────────────────────────────────────▶           │   │
  │                │  └────────────────────────────────────────────────────────────────────────┘   │
  │                │               │               │               │               │               │
  │                │──complete_scan_run─────────────────────────────────────────────▶               │
  │                │──export_evaluation_excel──────────────────────────────────────────────────────▶│
  │                │──send_report_email────────────────────────────────────────────────────────────▶│
  │◀──done─────────│               │               │               │               │               │
```

---

## 6. 設定構成 (`config.yaml`)

```yaml
hrmos:                    # HRMOSの接続先URL
credentials:              # 認証情報（環境変数で上書き可）
evaluation_criteria:      # AI評価基準（name + description のリスト）
evaluation:               # AI評価の実行パラメータ
  system_instructions:    #   プロンプトに含むシステム指示
  max_retries: 3          #   Claude CLIリトライ回数
  retry_delay: 5          #   リトライ間隔（秒）
  timeout: 120            #   タイムアウト（秒）
  max_text_chars: 80000   #   テキスト最大文字数
  shell: false            #   subprocess の shell オプション
interview_questions:      # 面接質問生成設定
  count: 3                #   質問数
  perspective: |          #   質問の観点
scan:                     # スキャン実行設定
  download_dir:           #   書類保存先
  report_dir:             #   レポート出力先
  db_path:                #   SQLiteパス
  headless: false         #   ヘッドレスモード
email:                    # Resendメール通知（オプション）
```

### 環境変数によるオーバーライド

| 環境変数 | 対応する設定 |
|----------|-------------|
| `HRMOS_EMAIL` | `credentials.email` |
| `HRMOS_PASSWORD` | `credentials.password` |
| `RESEND_API_KEY` | `email.api_key` |

---

## 7. CLIコマンド体系

```
python run.py [--config CONFIG] [-v] {scan,report,status}

scan   [--all]              応募者書類をAI評価（--allで全員再評価）
report [--run-id ID]        評価結果をExcelに出力
status                      評価進捗状況を表示
```

```
run.py (argparse)
  │
  ├── scan   → main.run_scan()     ← async（Playwright）
  ├── report → main.run_report()   ← sync
  └── status → main.show_status()  ← sync
```

---

## 8. Excel出力フォーマット

```
┌──────┬────┬────┬──────────┬──────┬───────┬──────┬───────┬──────┬─────────┬──────┬──────┬──────┬──────┬──────┬──────┐
│応募者│性別│年齢│HRMOS URL │ファイル│基準1 │基準1 │基準2  │基準2 │ ...     │合計点│総合  │総合  │質問  │質問  │質問  │
│名    │    │    │          │名     │(点)  │(評価)│(点)  │(評価)│         │      │ランク│評価  │候補1 │候補2 │候補3 │
├──────┼────┼────┼──────────┼──────┼───────┼──────┼───────┼──────┼─────────┼──────┼──────┼──────┼──────┼──────┼──────┤
│山田  │男性│ 35 │https://..│xx.pdf│  4   │コメント│  3   │コメント│         │  24  │  A   │...   │...   │...   │...   │
│太郎  │    │    │          │      │      │      │      │      │         │      │      │      │      │      │      │
└──────┴────┴────┴──────────┴──────┴───────┴──────┴───────┴──────┴─────────┴──────┴──────┴──────┴──────┴──────┴──────┘
```

### 総合ランク算出ロジック

| ランク | 条件（平均点） | セル色 |
|--------|---------------|--------|
| S | avg >= 4.5 | 金 (#FFD700) |
| A | avg >= 3.5 | 水色 (#87CEEB) |
| B | avg >= 2.5 | 薄緑 (#90EE90) |
| C | avg >= 1.5 | 薄橙 (#FFE4B5) |
| D | avg < 1.5 | 薄赤 (#FFB6C1) |

---

## 9. エラーハンドリング方針

| レイヤー | エラー種別 | 対応 |
|---------|-----------|------|
| browser/auth | ログイン失敗 | 処理中断。セッションファイル削除で再試行 |
| browser/navigator | 要素未発見 | 該当応募者をスキップ、ログ警告 |
| parser/document | パース失敗 | 空テキスト返却、ログエラー |
| evaluator/claude_client | タイムアウト/CLIエラー | 最大3回リトライ後、該当応募者をスキップ |
| evaluator/response_parser | JSONパースエラー | `ParseError` 発生、該当応募者をスキップ |
| reporter/notify | メール送信失敗 | ログエラー（評価処理には影響しない） |

応募者単位でのエラーは `applicants.status = 'error'` に記録され、次回実行時に `pending` として再処理対象にはならない（`--all` で明示的にリセット可能）。
