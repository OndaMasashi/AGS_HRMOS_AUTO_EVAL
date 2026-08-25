@echo off
REM ============================================================
REM  HRMOS AI Evaluation Tool - Run a scan
REM
REM  ASCII-only on purpose: cmd.exe reads .bat files with the OEM
REM  code page, so non-ASCII text here would be garbled.
REM
REM  Two modes:
REM    (no argument)  interactive - prints progress and pauses at
REM                   the end so a person who double-clicked this
REM                   file can read the result.
REM    scheduled      quiet - never pauses. Used by Task Scheduler.
REM ============================================================
setlocal
cd /d "%~dp0"

set "QUIET="
if /i "%~1"=="scheduled" set "QUIET=1"

REM The native Claude Code install is not always on PATH for a task
REM started by the scheduler; add its default location if present.
if exist "%USERPROFILE%\.local\bin\claude.exe" set "PATH=%USERPROFILE%\.local\bin;%PATH%"

set "LOG_DIR=%~dp0data\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM %date%/%time% formats depend on the regional settings, so build the
REM timestamp with PowerShell instead of slicing those strings.
set "TIMESTAMP="
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TIMESTAMP=%%i"
if not defined TIMESTAMP set "TIMESTAMP=unknown"

set "LOG_FILE=%LOG_DIR%\scan_%TIMESTAMP%.log"

REM Force UTF-8 so Japanese log lines never raise UnicodeEncodeError
REM when Python writes to a redirected file.
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

if not exist "%~dp0.venv\Scripts\python.exe" (
    echo [ERROR] .venv not found. Run setup\install.bat first.>> "%LOG_FILE%" 2>&1
    echo [ERROR] .venv not found. Run setup\install.bat first.
    if not defined QUIET pause
    exit /b 1
)

if not defined QUIET (
    echo ============================================================
    echo   HRMOS - scanning for new applicants
    echo ============================================================
    echo.
    echo   This takes several minutes. Do NOT close this window.
    echo   Progress is written to:
    echo     %LOG_FILE%
    echo.
)

echo [%TIMESTAMP%] scan start>> "%LOG_FILE%" 2>&1

"%~dp0.venv\Scripts\python.exe" "%~dp0run.py" scan >> "%LOG_FILE%" 2>&1
set EXIT_CODE=%ERRORLEVEL%

echo [%date% %time%] scan end (exit code: %EXIT_CODE%)>> "%LOG_FILE%" 2>&1

REM Keep the log directory from growing without bound (60 days).
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -LiteralPath '%LOG_DIR%' -Filter 'scan_*.log' -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-60) } | Remove-Item -Force -ErrorAction SilentlyContinue" >nul 2>&1

if not defined QUIET (
    echo.
    if "%EXIT_CODE%"=="0" (
        echo   Done. Reports are in:
        echo     %~dp0data\reports
    ) else (
        echo   [ERROR] The scan failed ^(exit code %EXIT_CODE%^).
        echo   Open this log file and send it to the administrator:
        echo     %LOG_FILE%
    )
    echo.
    pause
)

exit /b %EXIT_CODE%
