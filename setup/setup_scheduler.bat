@echo off
REM ============================================================
REM  HRMOS AI Evaluation Tool - Register scheduled runs
REM
REM  ASCII-only launcher. The actual logic (and all Japanese
REM  messages) live in setup_scheduler.ps1.
REM
REM  Administrator rights are NOT required: the task runs as the
REM  current user when logged on.
REM ============================================================
setlocal
cd /d "%~dp0.."

title HRMOS AI Evaluation Tool - Scheduler

if not exist "%~dp0setup_scheduler.ps1" (
    echo [ERROR] setup_scheduler.ps1 was not found next to this file.
    pause
    exit /b 1
)

chcp 65001 >nul

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_scheduler.ps1" %*
set EXITCODE=%ERRORLEVEL%

echo.
pause
exit /b %EXITCODE%
