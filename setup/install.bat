@echo off
REM ============================================================
REM  HRMOS AI Evaluation Tool - Installer (launcher)
REM
REM  This file is intentionally ASCII-only. Japanese messages live
REM  in install.ps1, because cmd.exe reads .bat files with the OEM
REM  code page (cp932 on Japanese Windows) and would garble UTF-8.
REM
REM  This launcher lives in the setup\ folder; the project root is
REM  one level up. install.ps1 resolves the root on its own.
REM ============================================================
setlocal
cd /d "%~dp0.."

title HRMOS AI Evaluation Tool - Installer

if not exist "%~dp0install.ps1" (
    echo [ERROR] install.ps1 was not found next to install.bat.
    echo Extract the entire zip archive first, then run install.bat again.
    echo.
    pause
    exit /b 1
)

REM Switch the console to UTF-8 so Japanese messages from PowerShell and
REM Python render correctly instead of being mangled by the OEM code page.
chcp 65001 >nul

REM Strip Mark of the Web so extracted scripts are not blocked by Windows.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -LiteralPath '%~dp0..' -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue" >nul 2>&1

REM -ExecutionPolicy Bypass applies to this process only and does not
REM change any machine or user setting.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set EXITCODE=%ERRORLEVEL%

echo.
if not "%EXITCODE%"=="0" (
    echo Some checks did not pass. See the [NG] lines above for what to fix,
    echo then run this installer again.
)
pause
exit /b %EXITCODE%
