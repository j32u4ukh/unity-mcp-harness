# Harness 工作區環境：UNITY_MCP_HOME + local.env.ps1
# 由工作區 scripts  dot-source；勿手動修改 $HarnessRoot 邏輯。

$ErrorActionPreference = "Stop"

# 工作區根 = 含 config/ 與 build_goals.yaml 的目錄（scripts 的上一層）
$HarnessRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$env:UNITY_MCP_HOME = $HarnessRoot

$localEnv = Join-Path $HarnessRoot "config\local.env.ps1"
if (Test-Path -LiteralPath $localEnv) {
    . $localEnv
} else {
    Write-Warning "config\local.env.ps1 不存在；請編輯 Unity 路徑後再執行 start-unity.ps1"
}
