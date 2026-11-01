<#
    Claude API のキーを保存する（provider: "claude_api" で評価するときに使う）

    使い方（必ず自分で実行する。Claude Code に実行させるとキーが会話とログに残る）:
      powershell -ExecutionPolicy Bypass -File scripts\set-anthropic-key.ps1

    保存先はリポジトリの外:
      %LOCALAPPDATA%\hrmos-auto-eval\anthropic-api-key

    ユーザー環境変数 ANTHROPIC_API_KEY にしない理由:
      Claude Code は非対話モード（claude -p）でその変数があれば常に使うため、
      この PC のすべての claude -p がプランではなく API 課金に切り替わってしまう。

    評価のたびにファイルを読み直すので、書き直したあとの再起動は要らない。
    キーを消すときはファイルを削除する。
    開発者専用のため配布 zip には入れない（setup\build_dist.ps1 で除外）。
#>

$ErrorActionPreference = 'Stop'

$base = $env:LOCALAPPDATA
if (-not $base) { $base = Join-Path $env:USERPROFILE 'AppData\Local' }
$dir = Join-Path $base 'hrmos-auto-eval'
$path = Join-Path $dir 'anthropic-api-key'

Write-Host ''
Write-Host 'Claude Console（https://platform.claude.com）の API Keys で発行したキーを貼り付けて Enter を押してください。'
Write-Host '（入力した文字は画面に表示されません）'
$secure = Read-Host -AsSecureString 'APIキー'
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr).Trim()
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

if (-not $key) {
    Write-Host '何も入力されなかったため、保存しませんでした。' -ForegroundColor Yellow
    exit 1
}
# Admin キー（sk-ant-admin...）は組織の管理用で、評価（Messages API）には使えない。
# 置いておくと危険が増えるだけなので保存しない。
if ($key.StartsWith('sk-ant-admin')) {
    Write-Host 'これは Admin キーです。Console で通常の API キーを発行してください。保存しませんでした。' -ForegroundColor Yellow
    exit 1
}
# 評価側（src\evaluator\claude_api_client.py）と同じ形の検査。改行や全角文字が混ざったまま
# 保存すると、あとでエラー文にキーが載るおそれがある。
if ($key -cnotmatch '^sk-ant-[A-Za-z0-9_-]+$') {
    Write-Host 'Claude API のキーの形ではありません（sk-ant- で始まり、英数字と - _ だけのはず）。保存しませんでした。' -ForegroundColor Yellow
    exit 1
}

New-Item -ItemType Directory -Force -Path $dir | Out-Null
# BOM なしの UTF-8 で書く（BOM がキーの一部として読まれないように）
[IO.File]::WriteAllText($path, $key, (New-Object Text.UTF8Encoding $false))

Write-Host "保存しました（$($key.Length) 文字）: $path" -ForegroundColor Green
Write-Host 'キーの値そのものは表示していません。'
Write-Host '続けて .venv\Scripts\python.exe run.py doctor --skip-llm で「Claude APIキー」の行が OK になるか確認してください。'
