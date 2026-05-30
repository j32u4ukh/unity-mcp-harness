# 規劃 + dry-run（不呼叫 MCP 建構）
# Usage: .\scripts\harness-dry-run.ps1

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_env.ps1"

unity-mcp-harness --dry-run --replan @args
