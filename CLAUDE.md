# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HRMOS採用ページから応募者書類（PDF/Word/Excel）を自動取得し、Gemini API または Claude CLI でAI評価・スコアリングを行い、Excelレポートを出力するCLI自動化ツール。Windows 10/11 + Python 3.10+ 環境で動作する。社内の同僚PCへ zip で配布して使う。

## Commands

```bash
# セットアップ（配布先・開発機とも setup\install.bat が正）
setup\install.bat          # Python導入〜venv〜依存〜Chromium〜設定〜自己診断まで一括

# 手動セットアップ
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium

# 日常運用（書類DL → AI評価 → Excel出力）
python run.py scan

# 全応募者を再評価（評価基準変更時。HRMOSへ人数分アクセスするため要注意）
python run.py scan --all

# エラー応募者のリトライ
python run.py scan --retry-errors

# HRMOSへの自動NG評価登録を行わず、対象者をログに出すだけにする
# （hrmos_evaluation.enabled が true のときのみ意味がある）
python run.py scan --dry-run

# DB内の評価結果をExcel再出力（評価なし・AI呼び出しなし）
python run.py report
python run.py report --run-id <uuid>

# 進捗確認
python run.py status

# 環境の自己診断（10項目。--skip-llm でAI呼び出しを省略）
python run.py doctor
python run.py doctor --skip-llm

# デバッグログ
python run.py -v scan

# 配布パッケージの作成（setup/ に zip を出力）
powershell -ExecutionPolicy Bypass -File setup\build_dist.ps1
```

AI を呼び出すのは `scan` と `doctor`（`--skip-llm` なし）のみ。`report` / `status` / `doctor --skip-llm` は課金が発生しない。

テストは `tests/` に2件: `test_pii_masker.py`（PII マスキング）と `test_first_pass.py`（1次通過判定の4値と応募日時のパース）。**pytest は `requirements.txt` に含まれず `.venv` にも未導入のため、そのままでは実行できない**（`pip install pytest` が必要）。`test_first_pass.py` は pytest 固有の機能（fixture / parametrize）を使っていないので、クラスを直接インスタンス化してメソッドを呼ぶだけでも検証できる。

## Architecture

5層のレイヤードアーキテクチャ。処理フローは `run.py` → `src/main.py`（オーケストレーター）が各層を順次呼び出す。

```
CLI (run.py: argparse)
  └→ main.py: run_scan() / run_report() / show_status()
  |    ├→ browser/   : Playwright によるHRMOSログイン・応募者一覧巡回・添付DL・自動NG評価登録
  |    ├→ parser/    : PDF(pdfplumber) / DOCX(python-docx) / XLSX(openpyxl) → テキスト
  |    ├→ evaluator/ : PII マスキング → プロンプト構築 → LLM 呼び出し → JSON パース
  |    ├→ database/  : SQLite (Repository パターン)
  |    └→ reporter/  : Excel 出力（レーダーチャート・ランク色付き）+ Resend メール通知（評価結果サマリ・新規0件通知・失敗アラート）
  └→ doctor.py: 環境の自己診断（各層を横断して「実際に使えるか」を検証）
```

`setup/` は導入・配布のためのスクリプトと利用者向けドキュメント一式（本体コードではない）。

### LLM呼び出しの仕組み

`config.yaml` の `evaluation.provider` で3方式を切り替える。既定は `gemini_api`。

| provider | 実装 | 認証 | 備考 |
|---|---|---|---|
| `gemini_api` | `gemini_api_client.py` | 環境変数 `GEMINI_API_KEY` | REST API を urllib で直接呼ぶ。CLI・Node.js 不要で無人実行に強い。**既定** |
| `claude` | `claude_client.py` | Claude CLI の対話ログイン | `subprocess.run(["claude","-p"])`。npm 版は `claude.cmd` になり CreateProcess が解決できないため **ネイティブ版（`claude.exe`）が必要** |
| `gemini` | `gemini_client.py` | Gemini CLI | **非推奨**。個人アカウント向け提供は 2026-06-18 に終了 |

- PII マスキング (`pii_masker.py`): LLM送信前に氏名・電話・住所をマスク、応答後にアンマスク。**職歴・所属企業名・資格はマスクしない**（評価に必要なため）
- リトライ: 最大3回（`max_retries`）、タイムアウト300秒
- テキスト切り詰め: 80,000文字上限（`claude_client.MAX_TEXT_CHARS` のハードコード。`config.yaml` の `max_text_chars` は参照されていない）
- Claude CLI 呼び出し時は環境変数 `CLAUDECODE` を除去（ネストセッション防止）
- LLM を呼ぶ箇所はコード全体で `main.py`（評価）と `doctor.py`（疎通確認）の2箇所のみ

### 設定の検証

`config.py` の `validate_config()` / `normalize_config()` が唯一の検証箇所。`load_config()` と `doctor.py` の両方から呼ぶ。**doctor が OK なのに scan が落ちる状態を作らないため、検証ロジックをここ以外に書かないこと。**

### データベース（SQLite）

4テーブル: `applicants`（応募者マスタ）、`documents`（添付書類）、`evaluations`（評価結果）、`scan_runs`（実行履歴）。evaluations は1応募者×評価基準数の行が入る（共通情報は各行に重複格納）。applicants の status は `pending` → `scanned` | `error` に遷移。`--all` で全員 `pending` にリセット。

### Excel出力

列構成: 基本情報 → 1次通過候補 → 平均点 → 合計点 → 総合ランク(S/A/B/C/D) → レーダーチャート → 総合評価 → 各評価基準(点・コメント) → 備考欄 → 質問候補。ランクは平均点で算出し、セル色を条件付きで設定。

「1次通過候補」列は `classify_first_pass()` の4値を出す: `○`（緑）/ `△`（薄黄）/ `×`（色なし）/ `？`（薄灰＝年齢不明・年齢帯外で**判定できなかった**）。`×` と `？` は意味が違う（前者はAIの点数が基準未満、後者は点数を見ていない）ため必ず別表示にすること。**セル自体が応募者ページへのハイパーリンク**で、○ 以外も1クリックで開ける。

## Key Configuration

`config.yaml`（`.gitignore` 対象、テンプレートは `config.yaml.example`）:
- `credentials`: HRMOS ログイン情報（環境変数 `HRMOS_EMAIL` / `HRMOS_PASSWORD` で上書き可）
- `evaluation_criteria`: 評価基準リスト（name + description）。項目数・内容は自由に変更可
- `evaluation.provider`: `"gemini_api"`（既定）/ `"claude"` / `"gemini"`（非推奨）
- `evaluation.model`: `gemini_api` のときのモデル。既定 `gemini-3.5-flash-lite`（同単価の `gemini-2.5-flash` より実測で約5倍速く、既存評価との一致度も高い）
- `evaluation.gemini_api_key`: 環境変数 `GEMINI_API_KEY` での指定を推奨
- `first_pass_criteria`: 年齢帯×平均点閾値による1次通過判定
- `interview_questions.perspective`: 面接質問生成の観点
- `email.attach_resumes`: `true`（デフォルト）で1次通過候補(○)の経歴書をメール添付。経歴書はマスクなしPIIを含むため運用注意
- `email.notify_on_no_candidates`: `true`（デフォルト）で新規応募者0件の正常終了時も「新規なし」通知を送る（無音による誤認防止）。失敗アラート（認証失敗・一覧0件・評価成功0件・例外）は `email.enabled` のみで常時送信
- `hrmos_evaluation`: HRMOS 上での自動NG評価登録。**配布時は OFF**（`enabled: false` / `dry_run: true`）。対象は1次通過候補が○にならなかった応募者のうち、**年齢から判定できた人（× と △）だけ**。年齢不明・年齢帯外は「判定不能」として対象外にする（点数と無関係に落とさないため）。`max_age_days`（既定3日）以内の応募に限定し、`max_per_run` で1実行あたりの上限を設ける。`--all` では登録しない。結果は `applicants.hrmos_eval_status` に記録して二重登録を防ぐ

## Conventions

- 言語: コード内コメント・ログ・ドキュメントはすべて日本語
- セッション管理: `storage_state.json` に Playwright セッションを保存。セッション有効性は URL 判定だけでなく応募者一覧（`/interviews/screening/` リンク）の描画有無まで確認し、失効途中（URL は正常だが一覧が空）でも自動再ログインする（`browser/auth.py`）。ログイン失敗時はこのファイルを削除して再実行
- 実行時生成物: `data/` 配下（downloads / reports / logs / debug / hrmos.db）は `.gitignore` 対象。`debug/` は応募者0件など異常時の画面・HTML（`applicant_list_empty_*.png/.html`）の保存先で原因切り分け用
- CSSセレクタ: HRMOS ページの要素セレクタは `browser/selectors.py` に集約。UI変更時はここを修正
- HRMOS への書き込みは `browser/evaluation_form.py` だけに閉じる。`navigator.py` は読み取り専用のまま保つ（誤って評価を登録し得る経路を1箇所に限定するため）。書き込み系では「判断に迷ったら登録しない」側に倒し、要素が1つに絞れないときは操作せず失敗させる
- ページ遷移: `page.goto()` を直接呼ばず `browser/page_utils.py` の `goto_with_retry()` を使う。`wait_until="networkidle"` の一発勝負は一時的な遅延で実行全体を落とすため、遷移は `domcontentloaded` で成立させ、`networkidle` は未到達でも続行する扱いにしている（遷移失敗のみ最大3回試行＝初回＋リトライ2回）。描画完了が必須の箇所は `ready_selector` で要素の出現を待つ
- 改修履歴: `improvement_list/` に `YYYY-MM-DD_{説明}.md` 形式で記録。未対応タスクは `ROADMAP.md` の上部に残す
- 認証情報: `config.yaml` に平文で書かない。`install.bat` は Windows のユーザー環境変数（`HRMOS_EMAIL` / `HRMOS_PASSWORD` / `GEMINI_API_KEY`）に保存する。フォルダごとコピーしても持ち出されないようにするため
- スクリプトの文字コード: `.bat` は**純ASCII + CRLF**（cmd.exe は OEM コードページで読むため日本語は文字化けする）、`.ps1` は **UTF-8 BOM + CRLF**。日本語メッセージは必ず `.ps1` 側に置く
- PowerShell は **Windows PowerShell 5.1** 前提（配布先に PS7 は無い）。`&&` / `??` / 三項演算子は使えない。`$ErrorActionPreference='Stop'` 下ではネイティブコマンドの stderr が致命的エラーになるため、外部コマンドは `Invoke-Native` で包む
- 配布: `setup/build_dist.ps1` で作る。手作業で zip 化しない。ビルド時に「機密の中身スキャン・入れ子の複製検出・件数チェック・必須ファイルの入れ忘れ検知・HTMLへの `<head>` 付与」が走る
- 利用者向けドキュメントは `setup/` の3つのHTML（`SETUP_GUIDE.html` / `SETUP_GUIDE.ADVANCED.html` / `OVERVIEW.html`）が正。`README.md` は開発者向けで**配布物には含めない**。Artifact 公開用に `<title>` から始まる断片で保存しており、`<head>` はビルド時に付与される
