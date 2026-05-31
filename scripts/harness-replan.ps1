# 重算 task_list 並預覽（等同 --replan-and-run --dry-run，不連 Unity 建構）
# Usage: .\scripts\harness-replan.ps1
# 重算後立刻開工: unity-mcp-harness --replan-and-run

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_env.ps1"

unity-mcp-harness --replan-and-run --dry-run @args
