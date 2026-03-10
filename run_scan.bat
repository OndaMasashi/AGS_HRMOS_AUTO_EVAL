@echo off
cd /d "%~dp0"

set LOG_DIR=%~dp0data\logs
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

set TIMESTAMP=%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%
set TIMESTAMP=%TIMESTAMP: =0%
set LOG_FILE=%LOG_DIR%\scan_%TIMESTAMP%.log

echo [%date% %time%] scan start >> "%LOG_FILE%" 2>&1

if not exist .venv\Scripts\python.exe (
    echo [ERROR] .venv not found >> "%LOG_FILE%" 2>&1
    exit /b 1
)

.venv\Scripts\python.exe run.py scan >> "%LOG_FILE%" 2>&1
set EXIT_CODE=%ERRORLEVEL%

echo [%date% %time%] scan end (exit code: %EXIT_CODE%) >> "%LOG_FILE%" 2>&1
exit /b %EXIT_CODE%