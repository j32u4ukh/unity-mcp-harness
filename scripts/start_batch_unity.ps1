# Start Unity in batch mode (headless) for MCP Server.
# Usage:
#   .\scripts\start_batch_unity.ps1
#   .\scripts\start_batch_unity.ps1 -ProjectPath "D:\OtherProject"

param(
    [string]$UnityExe = "C:\Program Files\Unity\Hub\Editor\6000.4.8f1\Editor\Unity.exe",
    [string]$ProjectPath = "C:\Users\PC\Documents\UnityProjects\PlanetaryMalignancy"
)

# 強制設定 PowerShell 階段的所有輸出編碼為 UTF-8 (必須放在 param 之後)
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ErrorActionPreference = "Stop"

# 1. Check Paths
if (-not (Test-Path -LiteralPath $UnityExe)) {
    Write-Error "Unity executable not found at: $UnityExe"
}
if (-not (Test-Path -LiteralPath $ProjectPath)) {
    Write-Error "Unity Project path not found at: $ProjectPath"
}

# 2. Setup Log Directory and Clean Old Logs
$logDir = Join-Path $ProjectPath "Logs"
if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}
$logFile = Join-Path $logDir "unity-batch.log"
if (Test-Path -LiteralPath $logFile) {
    Remove-Item -LiteralPath $logFile -Force -ErrorAction SilentlyContinue
}

# 3. Core Arguments (Kept GPU active for URP 2D and AI Assistant)
$unityArgs = @(
    "-batchmode",
    "-projectPath", "`"$ProjectPath`"",
    "-logFile", "`"$logFile`""
)

Write-Host "Checking for existing Unity processes..." -ForegroundColor Cyan

$existingUnity = Get-Process -Name "Unity" -ErrorAction SilentlyContinue
if ($existingUnity) {
    Write-Warning "Warning: Another Unity Editor instance is running. Please ensure it is closed, or batch mode may fail due to project locking."
}

Write-Host "Launching Unity in Background..." -ForegroundColor Green

# 4. Start Process & Capture Process Object (使用 -PassThru 抓取 PID)
$unityProcess = Start-Process -FilePath $UnityExe -ArgumentList $unityArgs -WorkingDirectory $ProjectPath -NoNewWindow -PassThru

# 立即提取 PID
$unityPID = $unityProcess.Id
Write-Host "Unity process launched successfully with PID: $unityPID" -ForegroundColor Green

# 5. Runtime Tracking (Wait 3 seconds and peek into logs)
Write-Host "Waiting 3 seconds for project initialization..." -ForegroundColor Cyan
Start-Sleep -Seconds 3

# 進階驗證：檢查進程是否還活著（防範專案鎖定導致的瞬間閃退）
if ($unityProcess.HasExited) {
    Write-Error "Error: Unity process (PID: $unityPID) crashed or exited prematurely! Please check Unity hub or file locks."
}

if (Test-Path -LiteralPath $logFile) {
    Write-Host "Successfully initialized! Current Log Status:" -ForegroundColor Yellow
    Get-Content -LiteralPath $logFile -Tail 5
} else {
    Write-Warning "Warning: Log file not established yet. Unity might still be loading or encountered a launch error."
}

Write-Host "`nUnity started (batchmode)" -ForegroundColor Green
Write-Host "  PID:     $unityPID" -ForegroundColor Yellow
Write-Host "  exe:     $UnityExe"
Write-Host "  project: $ProjectPath"
Write-Host "  log:     $logFile"
Write-Host "------------------------------------------------"
Write-Host "Notice: Run [.\scripts\finish_batch_unity.ps1] to stop the background server after testing." -ForegroundColor Cyan