# 本機絕對路徑（勿提交版控；init 後請依環境修改）
$UnityProjectPath = "C:\Path\To\Your\UnityProject"
$UnityEditorPath  = "C:\Program Files\Unity\Hub\Editor\6000.0.0f1\Editor\Unity.exe"

# IvanMurzak Unity-MCP-Server（Harness autostart 與 scripts/start-unity-mcp-server.ps1）
$UnityMcpServerHome = "C:\Users\PC\Documents\llm-server\Unity-MCP\Unity-MCP-Server"
$env:UNITY_MCP_SERVER_HOME = $UnityMcpServerHome
