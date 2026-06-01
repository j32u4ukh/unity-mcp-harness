# 預覽 build_goals → task_list（不連 Unity、不寫入除非去掉 --dry-run）
# Usage: .\scripts\harness-replan.ps1
# 實際寫入隊列: unity-mcp-harness --goals build
# 寫入後執行建構: unity-mcp-harness

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_env.ps1"

unity-mcp-harness --goals build --dry-run @args
