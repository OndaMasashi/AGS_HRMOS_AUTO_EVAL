<#
    配布用 zip の作成

    手作業でのzip化は「新しいファイルを入れ忘れる」「機密ファイルを混ぜる」事故が
    起きやすいため、Git の管理対象を基準に機械的に組み立てる。

    使い方:
      powershell -ExecutionPolicy Bypass -File build_dist.ps1

    含めるもの : Git 管理下のファイル（= .gitignore で除外されていないもの）
    除外するもの: config.yaml / storage_state.json / data/ / .venv/ （機密・実行時生成物）
                  および過去の配布 zip 自身
#>

[CmdletBinding()]
param(
    # 既定は setup フォルダ自身。同僚へ渡す3点（zip / SETUP_GUIDE.html / OVERVIEW.html）が
    # 1箇所に揃うようにするため。
    [string]$OutputDir = ''
)

$ErrorActionPreference = 'Stop'

# このスクリプトは setup\ 配下にあるため、プロジェクトルートは1つ上の階層
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
Set-Location $Root

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host '[NG] git が見つかりません。Git for Windows を導入してください。' -ForegroundColor Red
    exit 1
}

# 配布物に絶対に混ぜてはいけないもの（混入すると認証情報・応募者情報が流出する）
$Forbidden = @(
    'config.yaml',
    'storage_state.json'
)
$ForbiddenPrefix = @(
    'data/',
    '.venv/',
    'improvement_list/',
    'note/',
    '.claude/',         # 開発用のエディタ設定。配布先には不要
    'tests/',           # テストコード。配布先では実行しない
    'docs/'             # 開発資料。利用者向けの説明は setup/OVERVIEW.html に集約済み
)

# 開発専用のため配布しないファイル（動作には影響しない）
$ForbiddenExact = @(
    'CLAUDE.md',
    'docs/package.json',
    'docs/package-lock.json',
    'docs/generate_report.js',
    'setup/DISTRIBUTION.md',  # 配る側の手順書。受け取る側には不要
    'ROADMAP.md',             # 開発中の未対応タスク。担当者名やメールが載る
    'README.md',              # 開発者向け。利用者向けの内容は setup/ の3つのHTMLに集約済み
    '.gitignore'              # Git 用。配布先には無意味
)

Write-Host ''
Write-Host '=== 配布パッケージの作成 ===' -ForegroundColor White
Write-Host ''

# core.quotepath=false を付けないと日本語ファイル名が "\346\..." 形式で返り、
# そのままではパスとして扱えない。git の出力は UTF-8 なので明示的に読み替える。
$prevEncoding = [Console]::OutputEncoding
try {
    [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false
    $tracked = & git -c core.quotepath=false ls-files
} finally {
    [Console]::OutputEncoding = $prevEncoding
}
if ($LASTEXITCODE -ne 0) {
    Write-Host '[NG] git ls-files に失敗しました。' -ForegroundColor Red
    exit 1
}

$files = New-Object System.Collections.Generic.List[string]
$skipped = New-Object System.Collections.Generic.List[string]

foreach ($f in $tracked) {
    if ([string]::IsNullOrWhiteSpace($f)) { continue }

    # 過去の配布 zip はリポジトリに残っていても同梱しない
    if ($f -like '*.zip') { $skipped.Add($f); continue }

    # setup/ の下にプロジェクトの複製が紛れ込むことがある（展開物の置き忘れ等）。
    # 入れ子のまま配ると同じファイルが二重に届くので、名前で確実に弾く。
    if ($f -like '*/AGS_HRMOS_AUTO_EVAL/*') { $skipped.Add($f); continue }

    $isForbidden = $false
    foreach ($x in $Forbidden) { if ($f -eq $x) { $isForbidden = $true } }
    foreach ($x in $ForbiddenExact) { if ($f -eq $x) { $isForbidden = $true } }
    foreach ($p in $ForbiddenPrefix) { if ($f -like "$p*") { $isForbidden = $true } }
    if ($isForbidden) { $skipped.Add($f); continue }

    if (Test-Path $f) {
        $files.Add($f)
    } else {
        Write-Host "  [注意] 管理対象だが実体がありません: $f" -ForegroundColor Yellow
    }
}

# 配布に必須のファイルが揃っているかを確認する（入れ忘れ検知）
$required = @(
    'setup/install.bat', 'setup/install.ps1', 'run_scan.bat',
    'setup/setup_scheduler.bat', 'setup/setup_scheduler.ps1',
    'requirements.txt', 'config.yaml.example', 'run.py', 'はじめにお読みください.txt', 'setup/SETUP_GUIDE.html', 'setup/SETUP_GUIDE.ADVANCED.html', 'setup/OVERVIEW.html'
)
$missing = @()
foreach ($r in $required) { if ($files -notcontains $r) { $missing += $r } }
if ($missing.Count -gt 0) {
    Write-Host "[NG] 配布に必要なファイルが Git 管理下にありません: $($missing -join ', ')" -ForegroundColor Red
    Write-Host '     git add してから再実行してください。' -ForegroundColor Red
    exit 1
}

# 念のため中身も検査する（誤って追跡された機密ファイルの検知）
foreach ($f in $files) {
    if ($f -like '*storage_state*' -or $f -eq 'config.yaml') {
        Write-Host "[NG] 機密ファイルが配布対象に含まれています: $f" -ForegroundColor Red
        exit 1
    }
}

$stamp = Get-Date -Format 'yyyyMMdd'
$stageRoot = Join-Path $env:TEMP ("hrmos_dist_" + [Guid]::NewGuid().ToString('N').Substring(0, 8))
$stage = Join-Path $stageRoot 'AGS_HRMOS_AUTO_EVAL'
New-Item -ItemType Directory -Path $stage -Force | Out-Null

try {
    foreach ($f in $files) {
        $dest = Join-Path $stage $f
        $destDir = Split-Path -Parent $dest
        if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
        Copy-Item -LiteralPath $f -Destination $dest -Force
    }

    if ([string]::IsNullOrWhiteSpace($OutputDir)) {
        $outDir = $ScriptDir
    } elseif ([IO.Path]::IsPathRooted($OutputDir)) {
        $outDir = $OutputDir
    } else {
        $outDir = Join-Path $Root $OutputDir
    }
    # --- 配布するHTMLに正しい <head> を付与する ---
    # 元ファイルは Artifact 公開用に <title> から始まる断片で保存している。
    # そのままローカルでダブルクリックすると charset 未指定のため、
    # 日本語Windowsでは Shift_JIS と誤認されて文字化けする。
    # viewport が無いとスマートフォンでも極端に縮小されて読めない。
    foreach ($h in @('setup/SETUP_GUIDE.html', 'setup/SETUP_GUIDE.ADVANCED.html', 'setup/OVERVIEW.html')) {
        $target = Join-Path $stage $h
        if (-not (Test-Path $target)) { continue }
        $inner = [IO.File]::ReadAllText($target, [Text.Encoding]::UTF8)
        if ($inner -match '(?i)^\s*<!doctype') { continue }   # 既に整形済みなら触らない
        $titleMatch = [regex]::Match($inner, '(?is)<title>(.*?)</title>')
        $pageTitle = if ($titleMatch.Success) { $titleMatch.Groups[1].Value } else { 'HRMOS評価ツール' }
        $head = @"
<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$pageTitle</title>
</head>
<body>
"@
        # 元の <title> は head 側に移したので本文からは取り除く
        $inner = [regex]::Replace($inner, '(?is)<title>.*?</title>\s*', '')
        $utf8 = New-Object Text.UTF8Encoding $false
        [IO.File]::WriteAllText($target, $head + $inner + "`r`n</body>`r`n</html>`r`n", $utf8)
    }
    Write-Host '  HTMLに<head>を付与 : 3ファイル' -ForegroundColor Gray

    if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
    $zipPath = Join-Path $outDir "AGS_HRMOS_AUTO_EVAL_$stamp.zip"
    if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

    Compress-Archive -Path $stage -DestinationPath $zipPath -CompressionLevel Optimal

    # --- 中身の走査: ファイル名で弾けなかった機密が本文に残っていないか ---
    # 実際に config.yaml の値が README やメモに転記されている事故があるため、
    # ファイル名だけでなく全ファイルの中身をパターンで確認する。
    $leaks = @()
    $patterns = @{
        'Google APIキー' = 'AIza[0-9A-Za-z_\-]{30,}'
        'Resend APIキー' = 're_[0-9A-Za-z_\-]{20,}'
        'Anthropic APIキー' = 'sk-ant-[0-9A-Za-z_\-]{20,}'
        'メールアドレス' = '[0-9A-Za-z._%+\-]+@[0-9A-Za-z.\-]+\.[A-Za-z]{2,}'
    }
    # テンプレートに書いてある例示アドレスは除外する
    $allowMail = @('onboarding@resend.dev', 'your-email@example.com', 'security@anthropic.com')

    foreach ($f in $files) {
        $full = Join-Path $stage $f
        if (-not (Test-Path $full)) { continue }
        if ($f -match '\.(png|jpg|jpeg|gif|ico|zip|docx|xlsx|pdf|db)$') { continue }
        $content = ''
        try { $content = Get-Content -LiteralPath $full -Raw -Encoding UTF8 -ErrorAction Stop } catch { continue }
        if (-not $content) { continue }
        foreach ($name in $patterns.Keys) {
            foreach ($m in [regex]::Matches($content, $patterns[$name])) {
                $v = $m.Value
                if ($name -eq 'メールアドレス') {
                    if ($allowMail -contains $v) { continue }
                    if ($v -like '*@example.com' -or $v -like '*@example.jp') { continue }
                }
                $leaks += "$f : [$name] $v"
            }
        }
    }
    if ($leaks.Count -gt 0) {
        Write-Host ''
        Write-Host '[NG] 配布物の中身に機密らしき文字列が見つかりました。' -ForegroundColor Red
        foreach ($l in ($leaks | Select-Object -Unique)) { Write-Host "     $l" -ForegroundColor Red }
        Write-Host '     該当箇所を削除するか、build_dist.ps1 の除外リストに追加してください。' -ForegroundColor Red
        exit 1
    }
    Write-Host '  中身の機密スキャン : 検出なし' -ForegroundColor Gray

    # 想定外の混入を件数でも検知する（入れ子の複製が入ると倍増する）
    if ($files.Count -gt 60) {
        Write-Host ''
        Write-Host "[NG] 同梱ファイルが $($files.Count) 件と多すぎます（想定40件前後）。" -ForegroundColor Red
        Write-Host '     プロジェクトの複製や展開物が紛れ込んでいないか確認してください。' -ForegroundColor Red
        exit 1
    }

    $sizeKb = [Math]::Round((Get-Item $zipPath).Length / 1KB, 1)
    Write-Host "  同梱 : $($files.Count) ファイル" -ForegroundColor Green
    Write-Host "  除外 : $($skipped.Count) ファイル（機密・生成物）" -ForegroundColor Gray
    Write-Host ''
    Write-Host "  作成しました: $zipPath ($sizeKb KB)" -ForegroundColor Green
    Write-Host ''
    Write-Host '  ------------------------------------------------------------'
    Write-Host '  同僚へ渡すのは、この4点だけです' -ForegroundColor Cyan
    Write-Host '  ------------------------------------------------------------'
    $zipName = Split-Path $zipPath -Leaf
    $w = [Math]::Max($zipName.Length, 16)
    Write-Host ("    {0}  … ツール本体（これを展開して setup\install.bat を実行）" -f $zipName.PadRight($w))
    Write-Host ("    {0}  … 導入手順書（受け取った人が読む）" -f 'SETUP_GUIDE.html'.PadRight($w))
    Write-Host ("    {0}  … 設定ガイド応用編（評価基準を変えたい人向け）" -f 'SETUP_GUIDE.ADVANCED.html'.PadRight($w))
    Write-Host ("    {0}  … 機能とアーキテクチャの説明" -f 'OVERVIEW.html'.PadRight($w))
    Write-Host ''
    Write-Host "  いずれも $outDir にあります。" -ForegroundColor Gray
    Write-Host '  （install.bat などの他のファイルは zip の中に入っているため、渡す必要はありません）' -ForegroundColor Gray
    Write-Host ''
    Write-Host '  配布時の注意:' -ForegroundColor Yellow
    Write-Host '    受け取った人は zip を右クリック → プロパティ → 「許可する」に'
    Write-Host '    チェックを入れてから展開してください（未実施だと install.bat が'
    Write-Host '    Windows のセキュリティ警告でブロックされます）。'
    Write-Host ''
} finally {
    if (Test-Path $stageRoot) { Remove-Item $stageRoot -Recurse -Force -ErrorAction SilentlyContinue }
}
