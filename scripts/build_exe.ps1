# Build unity-mcp-build.exe (PyInstaller). Config YAML/JSON beside exe; no rebuild needed to edit tasks.
# Usage: pip install pyinstaller ; .\scripts\build_exe.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    Write-Error "Install PyInstaller first: pip install pyinstaller"
}

pyinstaller @(
    "--noconfirm",
    "--clean",
    "--name", "unity-mcp-build",
    "--console",
    "--paths", $Root,
    "--collect-submodules", "aicentral",
    "--collect-submodules", "langgraph",
    "--collect-submodules", "harness",
    "--collect-submodules", "core",
    "--hidden-import", "yaml",
    "--hidden-import", "httpx",
    "--hidden-import", "langgraph",
    "--hidden-import", "build_workflow",
    (Join-Path $Root "run_build.py")
)

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed with exit code $LASTEXITCODE"
}

Write-Host ""
Write-Host "Done. Copy these files into dist\unity-mcp-build\ before running the exe:"
Write-Host "  - build_goals.yaml"
Write-Host "  - unity_servers.json"
Write-Host "  - config\secret.yaml (optional: config\aicentral.yaml, or set AICENTRAL_HOME)"
Write-Host ""
Write-Host "Unity MCP: approve the fixed exe once in Editor - Project Settings - AI - Unity MCP (or enable Auto-approve)."
Write-Host "See docs\EXE.md for details."
