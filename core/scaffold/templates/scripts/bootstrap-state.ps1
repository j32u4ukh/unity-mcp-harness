# 唯讀 MCP 盤點既有 Unity 專案 → 寫入 project_state/
# 前置：--init、config\secret.yaml、config\local.env.ps1，Unity Editor 已開啟
# Usage: .\scripts\bootstrap-state.ps1

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_env.ps1"

unity-mcp-harness --bootstrap-state @args
