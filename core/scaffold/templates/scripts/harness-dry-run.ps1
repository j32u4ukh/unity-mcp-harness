# 預覽將執行的 task_list（預設不連 Unity、不重算藍圖）
# Usage: .\scripts\harness-dry-run.ps1
# 先重算隊列再預覽: .\scripts\harness-dry-run.ps1 -Replan

param(
    [switch]$Replan
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_env.ps1"

$extra = @("--dry-run")
if ($Replan) {
    $extra = @("--goals", "build", "--dry-run")
}

unity-mcp-harness @extra @args
