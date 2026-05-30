# 啟動 Unity Editor（batchmode，供 MCP relay 使用）
# Usage: .\scripts\start-unity.ps1

$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\_env.ps1"

if (-not $UnityEditorPath -or -not $UnityProjectPath) {
    Write-Error "請在 config\local.env.ps1 設定 `$UnityEditorPath 與 `$UnityProjectPath"
}
if (-not (Test-Path -LiteralPath $UnityEditorPath)) {
    Write-Error "Unity executable not found: $UnityEditorPath"
}
if (-not (Test-Path -LiteralPath $UnityProjectPath)) {
    Write-Error "Unity project not found: $UnityProjectPath"
}

$logDir = Join-Path $UnityProjectPath "Logs"
if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}
$logFile = Join-Path $logDir "unity-batch.log"
if (Test-Path -LiteralPath $logFile) {
    Remove-Item -LiteralPath $logFile -Force -ErrorAction SilentlyContinue
}

$unityArgs = @(
    "-batchmode",
    "-projectPath", "`"$UnityProjectPath`"",
    "-logFile", "`"$logFile`""
)

Write-Host "Launching Unity (batchmode)..." -ForegroundColor Green
$unityProcess = Start-Process -FilePath $UnityEditorPath -ArgumentList $unityArgs -WorkingDirectory $UnityProjectPath -NoNewWindow -PassThru
Start-Sleep -Seconds 3

if ($unityProcess.HasExited) {
    Write-Error "Unity exited early (PID $($unityProcess.Id)). Check $logFile"
}

Write-Host "Unity started — PID $($unityProcess.Id)" -ForegroundColor Green
Write-Host "  project: $UnityProjectPath"
Write-Host "  log:     $logFile"
Write-Host "Run .\scripts\stop-unity.ps1 when finished." -ForegroundColor Cyan
