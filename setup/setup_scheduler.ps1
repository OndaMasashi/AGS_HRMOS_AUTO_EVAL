<#
    タスクスケジューラ登録 - 平日 12:30 / 17:30 に run_scan.bat を実行する

    install.ps1 からも、setup_scheduler.bat からも呼ばれる共通処理。

    旧 setup_scheduler.bat からの変更点:
      - schtasks ではなく ScheduledTasks モジュールを使い、スリープ対策設定
        (StartWhenAvailable / WakeToRun / バッテリー条件) を登録と同時に適用する。
        schtasks で作り直すたびにこれらが既定値へ戻る問題を解消する。
      - タスク名にフォルダ名の接尾辞を付け、複数フォルダへ導入しても衝突しないようにする。
      - 管理者権限は不要（自分のユーザーとしてログオン時に実行する）。
#>

[CmdletBinding()]
param(
    # 確認プロンプトを出さない（install.ps1 から呼ぶとき）
    [switch]$Quiet,
    # 登録を解除する
    [switch]$Unregister
)

$ErrorActionPreference = 'Stop'

try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false } catch { }

# このスクリプトは setup\ 配下にあるため、プロジェクトルートは1つ上の階層
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$RunScan = Join-Path $Root 'run_scan.bat'

# 同一PCに複数フォルダで導入してもタスク名が衝突しないようにする
$suffix = (Split-Path $Root -Leaf) -replace '[^A-Za-z0-9]', ''
$tasks = @(
    @{ Name = "HRMOS_AutoEval_1230_$suffix"; Time = '12:30' },
    @{ Name = "HRMOS_AutoEval_1730_$suffix"; Time = '17:30' }
)

if ($Unregister) {
    foreach ($t in $tasks) {
        try {
            Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false -ErrorAction Stop
            Write-Host "  解除しました: $($t.Name)" -ForegroundColor Green
        } catch {
            Write-Host "  見つかりません: $($t.Name)" -ForegroundColor Gray
        }
    }
    exit 0
}

if (-not (Test-Path $RunScan)) {
    Write-Host "  [NG] run_scan.bat が見つかりません: $RunScan" -ForegroundColor Red
    exit 1
}

if (-not $Quiet) {
    Write-Host ''
    Write-Host '=== HRMOS AI自動評価 - 定期実行の登録 ===' -ForegroundColor White
    Write-Host ''
    Write-Host "  対象: $RunScan"
    Write-Host '  平日 12:30 と 17:30 に自動実行するタスクを登録します。'
    Write-Host ''
}

$failed = $false
foreach ($t in $tasks) {
    try {
        # 'scheduled' を渡すと run_scan.bat が無人モードになる（pause しない）
        $action = New-ScheduledTaskAction -Execute $RunScan -Argument 'scheduled' -WorkingDirectory $Root
        $trigger = New-ScheduledTaskTrigger -Weekly `
            -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $t.Time

        # スリープ・バッテリー起因の「無音の取りこぼし」を防ぐ設定を登録時に含める
        $settings = New-ScheduledTaskSettingsSet `
            -StartWhenAvailable `
            -WakeToRun `
            -DontStopIfGoingOnBatteries `
            -AllowStartIfOnBatteries `
            -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
            -MultipleInstances IgnoreNew

        Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger `
            -Settings $settings -Description 'HRMOS採用 応募者書類のAI自動評価' `
            -Force -ErrorAction Stop | Out-Null

        Write-Host "  OK   $($t.Name)  ($($t.Time))" -ForegroundColor Green
    } catch {
        $failed = $true
        Write-Host "  NG   $($t.Name): $($_.Exception.Message)" -ForegroundColor Red
    }
}

if (-not $failed) {
    Write-Host ''
    Write-Host '  スリープ復帰後の実行 (StartWhenAvailable) を有効にしています。' -ForegroundColor Gray
    Write-Host '  ※ WakeToRun は OS のスリープ解除タイマーが有効な環境でのみ機能します。' -ForegroundColor Gray
    Write-Host '     確認: powercfg /query SCHEME_CURRENT SUB_SLEEP RTCWAKE' -ForegroundColor Gray
    Write-Host ''
    Write-Host '  登録状況の確認:' -ForegroundColor Gray
    Write-Host "    Get-ScheduledTask -TaskName $($tasks[0].Name) | Get-ScheduledTaskInfo" -ForegroundColor Gray
    Write-Host '  解除:' -ForegroundColor Gray
    Write-Host '    powershell -ExecutionPolicy Bypass -File setup\setup_scheduler.ps1 -Unregister' -ForegroundColor Gray
}

if ($failed) { exit 1 }
exit 0
