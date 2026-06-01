# 執行 Harness 建構（依 task_list 順序）
# Usage: .\scripts\harness-run.ps1

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_env.ps1"

unity-mcp-harness --tasks run @args
