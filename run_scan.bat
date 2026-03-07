@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo [エラー] .venv が見つかりません。先に setup.bat を実行してください。
    pause
    exit /b 1
)
.venv\Scripts\python.exe run.py scan
if %ERRORLEVEL% NEQ 0 pause
