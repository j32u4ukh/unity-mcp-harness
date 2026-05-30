# 強制重跑 Plan Normalize 並重建 task_list
# Usage: .\scripts\harness-replan.ps1

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_env.ps1"

unity-mcp-harness --replan --dry-run @args
