<#
    HRMOS採用 応募者書類AI評価ツール - インストーラ本体

    install.bat から powershell -ExecutionPolicy Bypass -File 経由で起動される。
    Windows PowerShell 5.1 で動く構文のみを使う（&& / ?? / 三項演算子は使わない）。

    方針:
      - 素の Windows 11 を前提とし、必要な外部ソフト（Python）は自動導入する
      - 管理者権限は不要（すべてユーザースコープ）
      - 各ステップは「コマンドの終了コード」ではなく「目的物が実際に使えるか」で判定する
      - 認証情報は config.yaml に平文で書かず、ユーザー環境変数に保存する
#>

[CmdletBinding()]
param(
    # 対話入力を省略する（CI や再実行時の検証用）
    [switch]$NonInteractive,
    # 前提ソフトの自動インストールを行わない
    [switch]$SkipPrereq
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# 標準入力がコンソールでないときに対話入力へ進むと、Read-Host -AsSecureString が
# 「空を返す」のではなく**戻ってこない**（平文の Read-Host と挙動が違う）。
# パスワードとAPIキーの入力が該当するため、先に検出して非対話へ落とす。
if (-not $NonInteractive) {
    try {
        if ([Console]::IsInputRedirected) { $NonInteractive = $true }
    } catch { }
}

# 子プロセス(Python)の日本語出力が欠落しないよう、入出力をUTF-8に統一する。
# これを行わないと cp932 のコンソールを経由する際に文字が失われる。
try {
    [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false
    $OutputEncoding = New-Object Text.UTF8Encoding $false
} catch { }
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

# このスクリプトは setup\ 配下にあるため、プロジェクトルートは1つ上の階層になる
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
Set-Location $Root

$PythonSeries      = '3.13'
$PythonFullVersion = '3.13.15'
$WingetPythonId    = 'Python.Python.3.13'
# 既定モデル。gemini-2.5-flash と同単価だが実測で約5倍速い（3.9秒 vs 20.2秒/名）
$GeminiModel       = 'gemini-3.5-flash-lite'
$VenvPython        = Join-Path $Root '.venv\Scripts\python.exe'
$VenvPip           = Join-Path $Root '.venv\Scripts\pip.exe'

# ---------------------------------------------------------------- 表示ヘルパー

$script:StepNo = 0
$script:TotalSteps = 8

function Write-Step {
    param([string]$Message)
    $script:StepNo++
    Write-Host ''
    Write-Host ("[{0}/{1}] {2}" -f $script:StepNo, $script:TotalSteps, $Message) -ForegroundColor Cyan
}

function Write-Ok      { param([string]$m) Write-Host "      OK   $m" -ForegroundColor Green }
function Write-Info    { param([string]$m) Write-Host "           $m" -ForegroundColor Gray }
function Write-Warn2   { param([string]$m) Write-Host "      注意 $m" -ForegroundColor Yellow }
function Write-Fail    { param([string]$m) Write-Host "      NG   $m" -ForegroundColor Red }

function Invoke-Native {
    <#
        外部コマンドを実行する。Windows PowerShell 5.1 は $ErrorActionPreference='Stop' のとき
        ネイティブコマンドの標準エラー出力を致命的エラー(NativeCommandError)として扱うため、
        警告を出しただけのコマンドでスクリプト全体が止まってしまう。
        成否は終了コードや実物の存在確認で別途判定するので、ここでは止めない。
    #>
    param([scriptblock]$Script)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Script } finally { $ErrorActionPreference = $prev }
}

function Invoke-VenvPython {
    <#
        仮想環境の Python でスクリプトを実行し、標準出力だけを文字列で返す。
        標準エラーは判定に使わないため捨てる（上記の NativeCommandError 対策も兼ねる）。
    #>
    param([string]$Code)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = $Code | & $VenvPython - 2>$null
        return ($out -join "`n")
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Stop-WithError {
    param([string]$Message, [string[]]$Hints = @())
    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host "  セットアップを中断しました" -ForegroundColor Red
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host ''
    Write-Host "  原因: $Message"
    if ($Hints.Count -gt 0) {
        Write-Host ''
        Write-Host '  対処:'
        foreach ($h in $Hints) { Write-Host "    - $h" }
    }
    Write-Host ''
    Write-Host "  ログ: $script:LogPath"
    exit 1
}

# ------------------------------------------------------------------ ログ開始

$LogDir = Join-Path $Root 'data\logs'
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$script:LogPath = Join-Path $LogDir ("install_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
$script:LogOk = $false
try {
    Start-Transcript -Path $script:LogPath -Force | Out-Null
    $script:LogOk = $true
} catch {
    # トランスクリプトが取れなくても導入自体は続行する。
    # ただし「あるはずのログ」を案内すると調査を空振りさせるので記録しておく。
    $script:LogPath = '(ログの記録に失敗しました)'
}

Write-Host ''
Write-Host '============================================================' -ForegroundColor White
Write-Host '  HRMOS採用 応募者書類AI評価ツール - セットアップ' -ForegroundColor White
Write-Host '============================================================' -ForegroundColor White
Write-Host ''
Write-Host "  インストール先: $Root"
Write-Host "  ログ:           $script:LogPath"

# =====================================================  1. Python を確認・導入

function Get-UsablePython {
    <#
        実際に使える Python 3.10+ の実行ファイルパスを返す。
        Microsoft Store のアプリ実行エイリアス（WindowsApps 配下の 0 バイトスタブ）は
        「存在するのに動かない」ため必ず除外する。
    #>
    $candidates = New-Object System.Collections.Generic.List[string]

    # py ランチャーは PATH 更新の影響を受けにくいので最優先で試す
    $pyLauncher = Join-Path $env:WINDIR 'py.exe'
    if (Test-Path $pyLauncher) {
        foreach ($arg in @("-$PythonSeries", '-3')) {
            try {
                $resolved = Invoke-Native { & $pyLauncher $arg -c "import sys; print(sys.executable)" 2>$null }
                if ($LASTEXITCODE -eq 0 -and $resolved) { $candidates.Add($resolved.Trim()) }
            } catch { }
        }
    }

    # 既定のインストール先を直接探す（PATH がまだ更新されていない直後でも見つかる）
    $known = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python314\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
        'C:\Python313\python.exe'
    )
    foreach ($k in $known) { if (Test-Path $k) { $candidates.Add($k) } }

    # 最後に PATH 上の python
    foreach ($cmd in (Get-Command python -All -ErrorAction SilentlyContinue)) {
        if ($cmd.Source) { $candidates.Add($cmd.Source) }
    }

    foreach ($exe in $candidates) {
        if ([string]::IsNullOrWhiteSpace($exe)) { continue }
        if ($exe -like '*\WindowsApps\*') { continue }   # Store スタブ
        if (-not (Test-Path $exe)) { continue }
        try {
            $ver = Invoke-Native { & $exe -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null }
            if ($LASTEXITCODE -ne 0 -or -not $ver) { continue }
            $parts = $ver.Trim().Split('.')
            if ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 10) { return $exe }
        } catch { continue }
    }
    return $null
}

function Install-Python {
    Write-Info 'Python が見つからないため自動インストールを試みます。'

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Info "winget で $WingetPythonId を導入します（管理者権限は不要です）..."
        try {
            & winget install --id $WingetPythonId -e --source winget --scope user `
                --accept-package-agreements --accept-source-agreements | Out-Host
        } catch {
            Write-Warn2 "winget が失敗しました: $($_.Exception.Message)"
        }
        if (Get-UsablePython) { return $true }
        Write-Warn2 'winget では導入できませんでした。python.org から直接取得します。'
    } else {
        Write-Info 'winget が使えないため python.org から直接取得します。'
    }

    $url = "https://www.python.org/ftp/python/$PythonFullVersion/python-$PythonFullVersion-amd64.exe"
    $installer = Join-Path $env:TEMP "python-$PythonFullVersion-amd64.exe"
    try {
        Write-Info "ダウンロード中: $url"
        # Invoke-WebRequest 経由のダウンロードには Mark of the Web が付かない
        Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
        Write-Info 'インストール中（管理者権限は不要です）...'
        $p = Start-Process -FilePath $installer -Wait -PassThru -ArgumentList @(
            '/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_test=0'
        )
        Write-Info "インストーラ終了コード: $($p.ExitCode)"
    } catch {
        Stop-WithError "Python の自動インストールに失敗しました: $($_.Exception.Message)" @(
            "https://www.python.org/downloads/windows/ から Python $PythonSeries を手動でインストールしてください",
            'インストール時に「Add python.exe to PATH」に必ずチェックを入れてください',
            'その後 install.bat を再実行してください'
        )
    } finally {
        if (Test-Path $installer) { Remove-Item $installer -Force -ErrorAction SilentlyContinue }
    }

    return [bool](Get-UsablePython)
}

Write-Step 'Python を確認しています'

$python = Get-UsablePython
if (-not $python) {
    if ($SkipPrereq) {
        Stop-WithError 'Python が見つかりません（-SkipPrereq 指定のため自動導入をスキップしました）。'
    }
    if (Install-Python) { $python = Get-UsablePython }
}

if (-not $python) {
    Stop-WithError 'Python をインストールしましたが、この画面からはまだ見つけられません。' @(
        'これは異常ではありません。PATH の変更は新しく開いた画面にしか反映されないためです',
        'いま開いているウィンドウを閉じ、あらためて install.bat をダブルクリックしてください'
    )
}

$pythonVersion = (Invoke-Native { & $python --version 2>&1 }) -join ''
Write-Ok "$pythonVersion"
Write-Info $python

# ==========================================================  2. 仮想環境の作成

Write-Step '仮想環境 (.venv) を準備しています'

$VenvDir = Join-Path $Root '.venv'

function Test-VenvUsable {
    <#
        仮想環境が「実際に使えるか」を確かめる。
        python.exe の存在だけでは不十分で、インストール中にウィンドウを閉じるなどして
        中断されると、python.exe はあるのに pip が壊れた状態が残る。
        その状態を「既存の仮想環境」として使い回すと、次の pip install が
        ModuleNotFoundError で失敗し、原因の分かりにくいエラーになる。
    #>
    if (-not (Test-Path $VenvPython)) { return $false }
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $null = & $VenvPython -m pip --version 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $prev
    }
}

if ((Test-Path $VenvDir) -and (-not (Test-VenvUsable))) {
    Write-Warn2 '既存の .venv が壊れている（前回の中断など）ため作り直します。'
    Remove-Item $VenvDir -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $VenvDir) {
        Stop-WithError '壊れた .venv フォルダを削除できませんでした。' @(
            'このツールを開いている画面やエディタをすべて閉じてください',
            "手動で $VenvDir フォルダを削除してから再実行してください"
        )
    }
}

if (Test-VenvUsable) {
    Write-Ok '既存の仮想環境を使用します。'
} else {
    Invoke-Native { & $python -m venv $VenvDir | Out-Host }
    if (-not (Test-VenvUsable)) {
        Stop-WithError '仮想環境を作成できませんでした。' @(
            'ウイルス対策ソフトが .venv の作成を妨げていないか確認してください',
            'フォルダをネットワークドライブや OneDrive 同期対象外の場所に置いて再実行してください',
            "うまくいかない場合は $VenvDir フォルダを削除してから再実行してください"
        )
    }
    Write-Ok '仮想環境を作成しました。'
}

# ==================================================  3. 依存パッケージの導入

Write-Step '依存パッケージをインストールしています'

Invoke-Native { & $VenvPython -m pip install --upgrade pip --disable-pip-version-check --quiet | Out-Host }
Invoke-Native { & $VenvPip install -r (Join-Path $Root 'requirements.txt') --disable-pip-version-check | Out-Host }

# pip の終了コードだけでなく、実際に import できるかで判定する
$importCheck = Invoke-VenvPython @"
import os, sys
missing = []
for mod in ('playwright', 'pdfplumber', 'docx', 'openpyxl', 'yaml', 'resend'):
    try:
        __import__(mod)
    except ImportError:
        missing.append(mod)
sys.stdout.write(','.join(missing))
sys.stdout.flush()
os._exit(0)
"@

if ($importCheck -and $importCheck.Trim()) {
    Stop-WithError "依存パッケージを読み込めません: $($importCheck.Trim())" @(
        'インターネット接続を確認してください',
        '社内プロキシがある場合は環境変数 HTTPS_PROXY を設定してから再実行してください',
        "手動実行: .venv\Scripts\pip.exe install -r requirements.txt"
    )
}
Write-Ok '6件すべて導入済みです。'

# =====================================================  4. Chromium の導入

Write-Step 'ブラウザ (Chromium) をインストールしています'
Write-Info '数百MBのダウンロードが発生するため数分かかることがあります。'

Invoke-Native { & $VenvPython -m playwright install chromium | Out-Host }

# sync_playwright はドライバプロセスを起動するため、終了時に asyncio の警告を
# 標準エラーへ出すことがある。os._exit(0) で終了処理を飛ばして警告を出させない。
$chromiumCheck = Invoke-VenvPython @"
import os, sys
from pathlib import Path
found = ''
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        exe = p.chromium.executable_path
    if exe and Path(exe).exists():
        found = exe
except Exception:
    pass
sys.stdout.write(found)
sys.stdout.flush()
os._exit(0)
"@

if (-not $chromiumCheck -or -not $chromiumCheck.Trim()) {
    Stop-WithError 'Chromium を導入できませんでした。' @(
        'インターネット接続・プロキシ設定を確認してください',
        "手動実行: .venv\Scripts\python.exe -m playwright install chromium"
    )
}
Write-Ok 'Chromium を導入しました。'

# =====================================================  5. 設定ファイルの準備

Write-Step '設定ファイルを準備しています'

$ConfigPath  = Join-Path $Root 'config.yaml'
$ExamplePath = Join-Path $Root 'config.yaml.example'

if (Test-Path $ConfigPath) {
    Write-Ok 'config.yaml は既に存在するため上書きしません。'
} else {
    if (-not (Test-Path $ExamplePath)) {
        Stop-WithError 'config.yaml.example が見つかりません。zip を展開し直してください。'
    }
    Copy-Item $ExamplePath $ConfigPath
    Write-Ok 'config.yaml.example から config.yaml を作成しました。'
}

foreach ($d in @('data\downloads', 'data\reports', 'data\logs')) {
    $full = Join-Path $Root $d
    if (-not (Test-Path $full)) { New-Item -ItemType Directory -Path $full -Force | Out-Null }
}
Write-Ok 'データ用フォルダを作成しました。'

# ===============================================  6. 認証情報の設定（対話）

function Set-UserEnv {
    <#
        ユーザー環境変数に保存し、同時に現在のプロセスにも反映する。
        （config.yaml に平文で書くとフォルダごとコピーした際に一緒に流出するため）
    #>
    param([string]$Name, [string]$Value)
    [Environment]::SetEnvironmentVariable($Name, $Value, 'User')
    Set-Item -Path "env:$Name" -Value $Value
}

function Read-RequiredValue {
    param([string]$Prompt, [switch]$Secret, [string]$Current)

    if ($Current) {
        $masked = '*' * [Math]::Min(8, $Current.Length)
        if ($Secret) {
            $shown = $masked
        } else {
            $shown = $Current
        }
        Write-Host "      現在の設定: $shown"
        $keep = Read-Host "      変更しますか？ 変更しない場合はそのまま Enter (y=変更)"
        if ($keep -ne 'y') { return $Current }
    }

    # 標準入力が閉じている状態（誤って非対話で起動された場合）に
    # Read-Host が即座に空を返し続けるため、試行回数で必ず打ち切る。
    for ($i = 1; $i -le 5; $i++) {
        if ($Secret) {
            $secure = Read-Host "      $Prompt" -AsSecureString
            $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
            try {
                $value = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
            } finally {
                [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
            }
        } else {
            $value = Read-Host "      $Prompt"
        }
        if ($value -and $value.Trim()) { return $value.Trim() }
        Write-Warn2 "入力が空です。もう一度入力してください。($i/5)"
    }

    Stop-WithError "$Prompt が入力されませんでした。" @(
        'install.bat をダブルクリックして、対話できる画面で実行してください',
        '入力を省略したい場合は、環境変数を手動で設定してから install.bat -NonInteractive を実行してください'
    )
}

function Get-ClaudeExe {
    <#
        claude.exe の実体パスを返す。インストール直後は PATH が未反映なので、
        既定のインストール先も直接見に行く。
        npm 版だと claude.cmd になり、Python の subprocess から呼べない
        （CreateProcess は .cmd を解決しないため）ので .exe のみを対象にする。
    #>
    $cmd = Get-Command claude.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return $cmd.Source }

    $known = @(
        (Join-Path $env:USERPROFILE '.local\bin\claude.exe'),
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\claude.exe')
    )
    foreach ($k in $known) { if (Test-Path $k) { return $k } }
    return $null
}

function Install-ClaudeCode {
    Write-Host ''
    $claude = Get-ClaudeExe

    if (-not $claude) {
        Write-Info 'Claude Code が見つかりません。インストールします（管理者権限は不要です）...'
        try {
            # 公式のネイティブインストーラ。%USERPROFILE%\.local\bin に入る
            Invoke-Native {
                & powershell -NoProfile -ExecutionPolicy Bypass -Command `
                    "irm https://claude.ai/install.ps1 | iex" | Out-Host
            }
        } catch {
            Write-Warn2 "インストールに失敗しました: $($_.Exception.Message)"
        }
        $claude = Get-ClaudeExe
    }

    if (-not $claude) {
        Write-Warn2 'Claude Code を自動で導入できませんでした。'
        Write-Host '           手動で次を実行してください（PowerShell）:'
        Write-Host '             irm https://claude.ai/install.ps1 | iex'
        Write-Host '           その後、この install.bat を再実行してください。'
        return
    }

    $version = (Invoke-Native { & $claude --version 2>$null }) -join ''
    Write-Ok "Claude Code: $version"
    Write-Info $claude

    # インストールされていても、初回のブラウザ認証が済んでいないと非対話実行は失敗する。
    # 「入っている＝使える」ではないので、実際に1回通して確かめる。
    #
    # 判定を「応答が空でないか」にしてはいけない。Claude Code は認証エラーなどの実行時失敗を
    # 標準出力に文章として返すことがあり、空判定では未認証を「ログイン済み」と誤判定する。
    # 合言葉を指定し、終了コード0かつその語が返ったときだけ成功とみなす。
    Write-Host ''
    Write-Info 'ログイン状態を確認しています（30秒ほどかかります）...'

    $job = Start-Job -ScriptBlock {
        param($exe)
        $env:CLAUDECODE = $null
        $text = 'Reply with exactly this word and nothing else: HRMOSOK' | & $exe -p 2>$null
        [pscustomobject]@{ Text = ($text -join ' '); Code = $LASTEXITCODE }
    } -ArgumentList $claude

    # 未認証時にブラウザ待ちで止まる可能性があるため、必ず時間で打ち切る
    $done = Wait-Job $job -Timeout 120
    $result = $null
    if ($done) { $result = Receive-Job $job -ErrorAction SilentlyContinue }
    Remove-Job $job -Force -ErrorAction SilentlyContinue

    if ($result -and $result.Code -eq 0 -and $result.Text -match 'HRMOSOK') {
        Write-Ok 'ログイン済みです。すぐに利用できます。'
        return
    }

    if (-not $done) {
        Write-Warn2 '確認が時間内に終わりませんでした（未ログインの可能性があります）。'
    } elseif ($result -and $result.Text -and $result.Text.Trim()) {
        # 応答はあるが合言葉が返らない＝認証エラー等の文章が返っている
        $head = $result.Text.Trim()
        if ($head.Length -gt 120) { $head = $head.Substring(0, 120) + '...' }
        Write-Warn2 "想定外の応答が返りました: $head"
    }

    Write-Host ''
    Write-Warn2 'まだブラウザでのログインが済んでいません。次の操作が必要です。'
    Write-Host ''
    Write-Host '           1) スタートメニューから「コマンド プロンプト」を開く'
    Write-Host '           2) 次の1行をそのままコピーして貼り付け、Enter を押す'
    Write-Host ''
    Write-Host "                `"$claude`"" -ForegroundColor Cyan
    Write-Host ''
    Write-Host '           3) 画面の案内に従い、ブラウザで Claude にログインする'
    Write-Host '              （初回はテーマ選択などの質問が出ます。Enter で進めて構いません）'
    Write-Host '           4) 終わったら exit と入力して閉じ、'
    Write-Host '              setup\install.bat をもう一度ダブルクリックする'
    Write-Host ''
    Write-Host '           ※ 2) で claude と入力せず、上の行をそのまま貼り付けてください。'
    Write-Host '              インストール直後は claude という短い名前では見つからないことがあります。'
    Write-Host '           ※ ログインは初回の1度だけです。'
    Write-Host '           ※ 評価の費用は契約中のプランに含まれ、追加請求はありません。'
}

Write-Step 'ログイン情報とAIの設定を行います'

if ($NonInteractive) {
    Write-Warn2 '対話入力をスキップしました（キーボード入力を受け取れない状態です）。'
    Write-Host '           認証情報は次の環境変数で設定してください:'
    Write-Host '             HRMOS_EMAIL / HRMOS_PASSWORD / GEMINI_API_KEY'
    Write-Host '           通常は setup\install.bat をダブルクリックして実行してください。'
} else {
    Write-Host ''
    Write-Host '  ここで入力した内容は config.yaml ではなく Windows のユーザー環境変数に'
    Write-Host '  保存されます（フォルダをコピーしても認証情報は持ち出されません）。'
    Write-Host ''

    Write-Host '  --- HRMOS採用のログイン情報 ---'
    Set-UserEnv 'HRMOS_EMAIL'    (Read-RequiredValue -Prompt 'メールアドレス' -Current $env:HRMOS_EMAIL)
    Set-UserEnv 'HRMOS_PASSWORD' (Read-RequiredValue -Prompt 'パスワード' -Secret -Current $env:HRMOS_PASSWORD)
    Write-Ok 'HRMOS のログイン情報を保存しました。'

    Write-Host ''
    Write-Host '  --- AI評価の設定 ---'
    Write-Host '  どちらのAIで評価するかを選びます。評価の精度に大きな差はありません。'
    Write-Host ''
    Write-Host '    1) Gemini（APIキー）' -ForegroundColor White
    Write-Host '       ・費用: 使った分だけ（応募者1名あたり約0.8円）'
    Write-Host '       ・必要: 会社のGoogleアカウントで発行したAPIキー（課金設定が有効なもの）'
    Write-Host '       ・特徴: 追加ソフト不要。ブラウザでのログイン作業もなし'
    Write-Host ''
    Write-Host '    2) Claude（サブスクリプション）' -ForegroundColor White
    Write-Host '       ・費用: 契約済みのプランに含まれます（使った分の追加請求はありません）'
    Write-Host '       ・必要: Claude の Pro / Max / Team / Enterprise 契約'
    Write-Host '       ・特徴: Claude Code の導入と、初回に1度だけブラウザでのログインが必要'
    Write-Host '       ・注意: 1つの契約を複数人で共有することは規約で禁止されています'
    Write-Host ''
    $choice = ''
    for ($i = 1; $i -le 5; $i++) {
        $raw = Read-Host '      番号を選んでください [1]'
        if (-not $raw) { $choice = '1'; break }
        # 全角数字で入力されることがあるため半角に寄せる
        $raw = $raw.Trim().Replace([char]0xFF11, '1').Replace([char]0xFF12, '2')
        if ($raw -eq '1' -or $raw -eq '2') { $choice = $raw; break }
        Write-Warn2 "1 か 2 を入力してください（入力された値: $raw）"
    }
    if (-not $choice) { $choice = '1'; Write-Warn2 '入力が確認できないため 1（Gemini）を選択します。' }

    if ($choice -eq '2') {
        $provider = 'claude'
        Write-Host ''
        Write-Ok 'Claude を使用します（評価の費用はサブスクリプションに含まれます）。'
        $script:ClaudeSelected = $true
    } else {
        $provider = 'gemini_api'
        Write-Host ''
        Write-Host '      APIキーは https://aistudio.google.com/apikey で取得できます。'
        Write-Host '      会社のGoogleアカウントでログインし「API キーを作成」を実行してください。'
        Write-Host ''
        Write-Warn2 '重要: そのキーのプロジェクトで「課金」が有効になっている必要があります。'
        Write-Host '           無料枠のキーは入力内容が学習に利用される規約のため、'
        Write-Host '           応募者の書類を扱う本ツールでは使用できません。'
        Write-Host ''
        Set-UserEnv 'GEMINI_API_KEY' (Read-RequiredValue -Prompt 'Gemini API キー' -Secret -Current $env:GEMINI_API_KEY)
        Write-Ok 'Gemini API キーを保存しました。'
    }

    # config.yaml を1行ずつ差し替える（YAML全体を再生成すると利用者の編集が消えるため）
    $configText = Get-Content $ConfigPath -Raw -Encoding UTF8
    $updated = [regex]::Replace(
        $configText, '(?m)^(\s*provider:\s*)"[^"]*"', ('${1}"' + $provider + '"'))
    if ($provider -eq 'gemini_api') {
        $updated = [regex]::Replace(
            $updated, '(?m)^(\s*model:\s*)"[^"]*"', ('${1}"' + $GeminiModel + '"'))
    }
    if ($updated -ne $configText) {
        [IO.File]::WriteAllText($ConfigPath, $updated, (New-Object Text.UTF8Encoding $false))
        Write-Ok "config.yaml を更新しました（provider: $provider）。"
    }

    if ($provider -eq 'claude') { Install-ClaudeCode }
}

# =========================================  7. 定期実行の登録（任意・対話）

Write-Step '定期実行の設定（任意）'

$registerScheduler = $false
if (-not $NonInteractive) {
    $ans = Read-Host '      平日 12:30 / 17:30 の自動実行を登録しますか？ (y/N)'
    if ($ans -eq 'y') { $registerScheduler = $true }
}

if ($registerScheduler) {
    # 登録ロジックは setup_scheduler.ps1 に集約している（単体でも実行できる）。
    # ここは任意ステップなので、失敗しても導入全体を止めない。
    $schedScript = Join-Path $ScriptDir 'setup_scheduler.ps1'
    try {
        if (-not (Test-Path $schedScript)) { throw "setup_scheduler.ps1 が見つかりません" }
        Invoke-Native { & $schedScript -Quiet }
        if ($LASTEXITCODE -ne 0) {
            Write-Warn2 '登録に失敗したタスクがあります。後から setup\setup_scheduler.bat を実行できます。'
        }
    } catch {
        Write-Warn2 "定期実行の登録をスキップしました: $($_.Exception.Message)"
        Write-Info '導入自体は続行します。後から setup\setup_scheduler.bat で登録できます。'
    }
} else {
    Write-Info '登録しませんでした。後から setup\setup_scheduler.bat を実行すれば登録できます。'
}

# =============================================================  8. 自己診断

Write-Step '環境を自己診断しています'

Invoke-Native { & $VenvPython (Join-Path $Root 'run.py') doctor | Out-Host }
$doctorExit = $LASTEXITCODE

Write-Host ''
Write-Host '============================================================' -ForegroundColor White
if ($doctorExit -eq 0) {
    Write-Host '  セットアップが完了しました' -ForegroundColor Green
    Write-Host '============================================================' -ForegroundColor White
    Write-Host ''
    Write-Host '  実行方法: run_scan.bat をダブルクリック'
    Write-Host '  再診断:   .venv\Scripts\python.exe run.py doctor'
} else {
    Write-Host '  セットアップは完了しましたが、未解決の項目があります' -ForegroundColor Yellow
    Write-Host '============================================================' -ForegroundColor White
    Write-Host ''
    Write-Host '  上の [NG] 行の指示に従って解消し、次のコマンドで再確認してください:'
    Write-Host '    .venv\Scripts\python.exe run.py doctor'
}
Write-Host ''
Write-Host "  ログ: $script:LogPath"
Write-Host ''

try { Stop-Transcript | Out-Null } catch { }
exit $doctorExit
