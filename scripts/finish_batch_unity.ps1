# Stop all Unity Editor processes safely with UTF-8 encoding.
# Usage: .\scripts\finish_batch_unity.ps1

$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ErrorActionPreference = "Stop"

Write-Host "Checking running Unity processes..." -ForegroundColor Cyan

$procs = Get-Process -Name "Unity" -ErrorAction SilentlyContinue

if (-not $procs) {
    Write-Host "Success: No running Unity.exe found in the system." -ForegroundColor Green
    exit 0
}

Write-Host "Warning: Found $($procs.Count) Unity process(es). Ready to terminate..." -ForegroundColor Yellow
Write-Host "------------------------------------------------"

foreach ($p in $procs) {
    try {
        $title = $p.MainWindowTitle
        if ([string]::IsNullOrEmpty($title)) { 
            $title = "Headless/MCP Server Mode" 
        }
        
        Write-Host "Terminating Unity -> [PID: $($p.Id)] ($title) ..." -ForegroundColor Yellow
        Stop-Process -Id $p.Id -Force -ErrorAction Stop
        Write-Host "  -> [PID: $($p.Id)] Terminated successfully." -ForegroundColor Green
    }
    catch {
        Write-Warning "  -> Failed to close PID $($p.Id). Error: $($_.Exception.Message)"
    }
}

Write-Host "------------------------------------------------"
Write-Host "Cleanup completed. All Unity.exe residual processes released." -ForegroundColor Green
Write-Host "Notice: You can now safely start a fresh Unity MCP session." -ForegroundColor Cyan