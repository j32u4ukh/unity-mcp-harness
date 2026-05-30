# 停止所有 Unity Editor 程序
# Usage: .\scripts\stop-unity.ps1

$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\_env.ps1"

Write-Host "Checking Unity processes..." -ForegroundColor Cyan
$procs = Get-Process -Name "Unity" -ErrorAction SilentlyContinue
if (-not $procs) {
    Write-Host "No Unity.exe running." -ForegroundColor Green
    exit 0
}

foreach ($p in $procs) {
    Write-Host "Stopping PID $($p.Id)..." -ForegroundColor Yellow
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
}
Write-Host "Done." -ForegroundColor Green
