# 補齊工作區範本（等同 unity-mcp-harness --init）
# Usage: .\scripts\setup.ps1

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_env.ps1"

Write-Host "Re-running workspace init (skip existing files)..." -ForegroundColor Cyan
unity-mcp-harness --init $HarnessRoot
Write-Host ""
Write-Host "若尚未設定，請編輯 config\secret.yaml 與 config\local.env.ps1" -ForegroundColor Yellow
