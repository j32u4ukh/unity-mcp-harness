# 列出 Unity MCP 工具（不呼叫 LLM）
# Usage: .\scripts\list-tools.ps1

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_env.ps1"

unity-mcp-list-tools --json
