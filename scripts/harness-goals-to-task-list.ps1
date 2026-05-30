# 僅將 build_goals.yaml 同步到 task_list.yaml（不跑 Unity MCP）
# Usage: .\scripts\harness-goals-to-task-list.ps1
# 寫回藍圖: .\scripts\harness-goals-to-task-list.ps1 -ExportGoalsFromTaskList

param(
    [switch]$ExportGoalsFromTaskList
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_env.ps1"

$extra = @("--goals-to-task-list")
if ($ExportGoalsFromTaskList) {
    $extra += "--export-goals-from-task-list"
}

unity-mcp-harness @extra @args
