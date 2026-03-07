@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo   HRMOS採用 応募者書類AI評価ツール - セットアップ
echo ============================================================
echo.

REM ============================================================
REM  Step 1: Python チェック
REM ============================================================
echo [Step 1/8] Python を確認中...

set PYTHON_CMD=
python --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PYTHON_CMD=python
) else (
    py --version >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set PYTHON_CMD=py
    )
)

if "%PYTHON_CMD%"=="" (
    echo.
    echo [エラー] Python が見つかりません。
    echo.
    echo 以下のいずれかの方法でインストールしてください:
    echo   1. winget install Python.Python.3.13
    echo   2. https://www.python.org/downloads/ からダウンロード
    echo.
    echo インストール後、再度 setup.bat を実行してください。
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('%PYTHON_CMD% --version 2^>^&1') do echo   %%v
echo [Step 1/8] Python ... OK
echo.

REM ============================================================
REM  Step 2: 仮想環境の作成
REM ============================================================
echo [Step 2/8] 仮想環境を作成中...

if exist .venv\Scripts\activate.bat (
    echo   仮想環境は既に存在します。スキップします。
) else (
    %PYTHON_CMD% -m venv .venv
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo [エラー] 仮想環境の作成に失敗しました。
        pause
        exit /b 1
    )
    echo   .venv を作成しました。
)
echo [Step 2/8] 仮想環境 ... OK
echo.

REM ============================================================
REM  Step 3: 依存パッケージのインストール
REM ============================================================
echo [Step 3/8] 依存パッケージをインストール中...

.venv\Scripts\pip.exe install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [エラー] パッケージのインストールに失敗しました。
    echo ネットワーク接続やプロキシ設定を確認してください。
    pause
    exit /b 1
)
echo [Step 3/8] 依存パッケージ ... OK
echo.

REM ============================================================
REM  Step 4: Playwright ブラウザのインストール
REM ============================================================
echo [Step 4/8] Chromium ブラウザをインストール中...
echo   （数分かかる場合があります）

.venv\Scripts\python.exe -m playwright install chromium
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [エラー] Chromium のインストールに失敗しました。
    echo ネットワーク接続を確認してください。
    pause
    exit /b 1
)
echo [Step 4/8] Chromium ... OK
echo.

REM ============================================================
REM  Step 5: config.yaml のコピー
REM ============================================================
echo [Step 5/8] 設定ファイルを準備中...

if exist config.yaml (
    echo   config.yaml は既に存在します。上書きしません。
) else (
    copy config.yaml.example config.yaml >nul
    echo   config.yaml を作成しました。
)
echo [Step 5/8] 設定ファイル ... OK
echo.

REM ============================================================
REM  Step 6: data ディレクトリの作成
REM ============================================================
echo [Step 6/8] データディレクトリを作成中...

if not exist data\downloads mkdir data\downloads
if not exist data\reports mkdir data\reports
echo [Step 6/8] データディレクトリ ... OK
echo.

REM ============================================================
REM  Step 7: Gemini CLI チェック
REM ============================================================
echo [Step 7/8] Gemini CLI を確認中...

where gemini >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo   Gemini CLI: OK
) else (
    echo   [注意] Gemini CLI が見つかりません。
    echo   以下のコマンドでインストールしてください:
    echo     npm install -g @google/gemini-cli
    echo   インストール後、ターミナルで gemini --version で確認できます。
)
echo [Step 7/8] Gemini CLI チェック ... 完了
echo.

REM ============================================================
REM  Step 8: 完了メッセージ
REM ============================================================
echo ============================================================
echo   セットアップが完了しました！
echo ============================================================
echo.
echo 次のステップ:
echo   1. config.yaml をテキストエディタで開き、以下を設定:
echo      - credentials.email / password（HRMOSログイン情報）
echo      - evaluation_criteria（評価基準、必要に応じて変更）
echo   2. 実行: run_scan.bat をダブルクリック
echo      または: .venv\Scripts\python.exe run.py scan
echo.
pause
