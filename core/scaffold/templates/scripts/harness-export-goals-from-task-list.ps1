# 將 task_list.yaml 規劃欄位寫回 build_goals.yaml（不規劃、不跑 Unity）
# Usage: .\scripts\harness-export-goals-from-task-list.ps1
# 寫回前備份: .\scripts\harness-export-goals-from-task-list.ps1 -Backup

param(
    [switch]$Backup
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_env.ps1"

$extra = @("--export-goals-from-task-list")
if ($Backup) {
    $extra += "--backup"
}

unity-mcp-harness @extra @args
