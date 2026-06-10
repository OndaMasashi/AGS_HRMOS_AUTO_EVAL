# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HRMOS採用ページから応募者書類（PDF/Word/Excel）を自動取得し、Claude CLI / Gemini CLIでAI評価・スコアリングを行い、Excelレポートを出力するCLI自動化ツール。Windows 10/11 + Python 3.10+ 環境で動作する。

## Commands

```bash
# セットアップ
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium

# 日常運用（書類DL → AI評価 → Excel出力）
python run.py scan

# 全応募者を再評価（評価基準変更時）
python run.py scan --all

# エラー応募者のリトライ
python run.py scan --retry-errors

# DB内の評価結果をExcel再出力（評価なし）
python run.py report
python run.py report --run-id <uuid>

# 進捗確認
python run.py status

# デバッグログ
python run.py -v scan
```

テストフレームワークは未導入。

## Architecture

5層のレイヤードアーキテクチャ。処理フローは `run.py` → `src/main.py`（オーケストレーター）が各層を順次呼び出す。

```
CLI (run.py: argparse)
  └→ main.py: run_scan() / run_report() / show_status()
       ├→ browser/   : Playwright によるHRMOSログイン・応募者一覧巡回・添付DL
       ├→ parser/    : PDF(pdfplumber) / DOCX(python-docx) / XLSX(openpyxl) → テキスト
       ├→ evaluator/ : PII マスキング → プロンプト構築 → LLM CLI subprocess → JSON パース
       ├→ database/  : SQLite (Repository パターン)
       └→ reporter/  : Excel 出力（レーダーチャート・ランク色付き）+ Resend メール通知（評価結果サマリ・新規0件通知・失敗アラート）
```

### LLM呼び出しの仕組み

APIキー不要。`subprocess.run()` で Claude CLI (`claude -p`) または Gemini CLI を呼び出す。stdin にプロンプトを送信し、stdout から JSON 応答を受け取る。`config.yaml` の `evaluation.provider` で切替。

- PII マスキング (`pii_masker.py`): LLM送信前に氏名・電話・住所をマスク、応答後にアンマスク
- リトライ: 最大3回（`max_retries`）、タイムアウト300秒
- テキスト切り詰め: 80,000文字上限
- Claude CLI 呼び出し時は環境変数 `CLAUDECODE` を除去（ネストセッション防止）

### データベース（SQLite）

4テーブル: `applicants`（応募者マスタ）、`documents`（添付書類）、`evaluations`（評価結果）、`scan_runs`（実行履歴）。evaluations は1応募者×評価基準数の行が入る（共通情報は各行に重複格納）。applicants の status は `pending` → `scanned` | `error` に遷移。`--all` で全員 `pending` にリセット。

### Excel出力

列構成: 基本情報 → 1次通過候補(○/△) → 平均点 → 合計点 → 総合ランク(S/A/B/C/D) → レーダーチャート → 総合評価 → 各評価基準(点・コメント) → 備考欄 → 質問候補。ランクは平均点で算出し、セル色を条件付きで設定。

## Key Configuration

`config.yaml`（`.gitignore` 対象、テンプレートは `config.yaml.example`）:
- `credentials`: HRMOS ログイン情報（環境変数 `HRMOS_EMAIL` / `HRMOS_PASSWORD` で上書き可）
- `evaluation_criteria`: 評価基準リスト（name + description）。項目数・内容は自由に変更可
- `evaluation.provider`: `"claude"` or `"gemini"`
- `first_pass_criteria`: 年齢帯×平均点閾値による1次通過判定
- `interview_questions.perspective`: 面接質問生成の観点
- `email.attach_resumes`: `true`（デフォルト）で1次通過候補(○)の経歴書をメール添付。経歴書はマスクなしPIIを含むため運用注意
- `email.notify_on_no_candidates`: `true`（デフォルト）で新規応募者0件の正常終了時も「新規なし」通知を送る（無音による誤認防止）。失敗アラート（認証失敗・一覧0件・評価成功0件・例外）は `email.enabled` のみで常時送信

## Conventions

- 言語: コード内コメント・ログ・ドキュメントはすべて日本語
- セッション管理: `storage_state.json` に Playwright セッションを保存。セッション有効性は URL 判定だけでなく応募者一覧（`/interviews/screening/` リンク）の描画有無まで確認し、失効途中（URL は正常だが一覧が空）でも自動再ログインする（`browser/auth.py`）。ログイン失敗時はこのファイルを削除して再実行
- 実行時生成物: `data/` 配下（downloads / reports / logs / debug / hrmos.db）は `.gitignore` 対象。`debug/` は応募者0件など異常時の画面・HTML（`applicant_list_empty_*.png/.html`）の保存先で原因切り分け用
- CSSセレクタ: HRMOS ページの要素セレクタは `browser/selectors.py` に集約。UI変更時はここを修正
- 改修履歴: `improvement_list/` に `YYYY-MM-DD_{説明}.md` 形式で記録
