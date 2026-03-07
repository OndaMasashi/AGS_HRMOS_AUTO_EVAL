@echo off
REM ============================================================
REM  HRMOS AI自動評価 - タスクスケジューラ登録スクリプト
REM  平日 12:30 と 17:30 に run_scan.bat を自動実行
REM  ※ 管理者権限で実行してください
REM ============================================================

set TASK_NAME_LUNCH=HRMOS_AutoEval_1230
set TASK_NAME_EVENING=HRMOS_AutoEval_1730
set BAT_PATH=%~dp0run_scan.bat

echo.
echo === HRMOS AI自動評価 タスクスケジューラ登録 ===
echo.

REM --- 既存タスクを削除（存在する場合） ---
schtasks /Delete /TN "%TASK_NAME_LUNCH%" /F >nul 2>&1
schtasks /Delete /TN "%TASK_NAME_EVENING%" /F >nul 2>&1

REM --- 平日 12:30 のタスク登録 ---
echo [1/2] 平日 12:30 のタスクを登録中...
schtasks /Create /TN "%TASK_NAME_LUNCH%" /TR "\"%BAT_PATH%\"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 12:30 /RL HIGHEST /F
if %ERRORLEVEL% NEQ 0 (
    echo [エラー] 12:30 のタスク登録に失敗しました。管理者権限で実行してください。
    pause
    exit /b 1
)

REM --- 平日 17:30 のタスク登録 ---
echo [2/2] 平日 17:30 のタスクを登録中...
schtasks /Create /TN "%TASK_NAME_EVENING%" /TR "\"%BAT_PATH%\"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 17:30 /RL HIGHEST /F
if %ERRORLEVEL% NEQ 0 (
    echo [エラー] 17:30 のタスク登録に失敗しました。管理者権限で実行してください。
    pause
    exit /b 1
)

echo.
echo === 登録完了 ===
echo.
echo 登録されたタスク:
schtasks /Query /TN "%TASK_NAME_LUNCH%" /FO LIST | findstr "タスク名 状態 次回"
echo.
schtasks /Query /TN "%TASK_NAME_EVENING%" /FO LIST | findstr "タスク名 状態 次回"
echo.
pause
