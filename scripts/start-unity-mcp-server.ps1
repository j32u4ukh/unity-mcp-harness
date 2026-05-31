# 常駐啟動 IvanMurzak Unity-MCP-Server（Streamable HTTP）
# 用法: .\scripts\start-unity-mcp-server.ps1 [-Port 22172] [-ServerHome "C:\path\to\Unity-MCP-Server"]

param(
    [int]$Port = 22172,
    [string]$ServerHome = $env:UNITY_MCP_SERVER_HOME
)

$ErrorActionPreference = "Stop"

if (-not $ServerHome) {
    $ServerHome = Join-Path (Split-Path $PSScriptRoot -Parent) "..\Unity-MCP\Unity-MCP-Server"
    $ServerHome = (Resolve-Path $ServerHome -ErrorAction SilentlyContinue).Path
}

if (-not $ServerHome -or -not (Test-Path $ServerHome)) {
    Write-Error "找不到 Unity-MCP-Server 目錄。請設 `$env:UNITY_MCP_SERVER_HOME 或 -ServerHome。"
}

Write-Host "Unity-MCP-Server @ $ServerHome (port $Port)"
Write-Host "MCP URL: http://localhost:$Port"
Write-Host "按 Ctrl+C 結束。"

Push-Location $ServerHome
try {
    dotnet run -- --port=$Port --client-transport=streamableHttp
}
finally {
    Pop-Location
}
