# IvanMurzak / Unity-MCP（Harness 整合）

Harness 未來預設透過 [IvanMurzak/Unity-MCP](https://github.com/IvanMurzak/Unity-MCP) 操作 Unity Editor。LangGraph 執行階段，AI Agent **只需**以標準 MCP **Streamable HTTP** 與本機 server 互動、發送 tool 指令。

## 連線拓撲

```
LangGraph + aicentral (Harness)
        │  MCP Streamable HTTP
        ▼
Unity-MCP-Server（dotnet，例如 :22172）
        │  plugin 通道（同 port）
        ▼
Unity Editor（Unity-MCP Plugin）
```

- **Client → Server**：Harness / aicentral 的 HTTP MCP（`unity_servers.json` 的 `url`）。
- **Server → Plugin**：Unity-MCP-Server 與 Editor 外掛必須使用**相同 port**（見 Plugin 與 Server 設定）。
- Agent **不**直接連 Editor；若 Server 程序未跑，HTTP 請求會立刻 `Connection refused`。

## 雞生蛋問題

若 `Unity-MCP-Server` **尚未**在 Windows 背景運行，`http://localhost:22172`（或你設定的 port）就是**死的**。LangGraph 一發 HTTP 請求就會 `ConnectionRefusedError`，整輪建構直接失敗。

**解法**：在 Harness 呼叫 MCP **之前**，先確保 Server 程序已監聽該 port。Harness 提供三種方式：

| 方式 | 說明 |
|------|------|
| **手動常駐** | 另開終端機啟動 Server，整輪建構期間保持運行 |
| **環境變數 autostart** | 設 `UNITY_MCP_SERVER_HOME`，Harness 在 port 未開時自動 `dotnet run` |
| **json autostart** | 在 `unity_servers.json` 的 server 項目加 `autostart` 區塊 |

## 手動啟動（建議先熟悉）

```powershell
cd C:\Users\PC\Documents\llm-server\Unity-MCP\Unity-MCP-Server
dotnet run -- --port=22172 --client-transport=streamableHttp
```

或使用工作區腳本：

```powershell
.\scripts\start-unity-mcp-server.ps1
```

驗證 port 已活：

```powershell
Invoke-WebRequest http://localhost:22172/help -UseBasicParsing
unity-mcp-list-tools --json
```

## unity_servers.json 範例

複製 `unity_servers.ivanmurzak.http.example.json` → `unity_servers.json`：

```json
{
  "unity": {
    "transport": "http",
    "url": "http://localhost:22172",
    "auth_type": "none",
    "description": "IvanMurzak Unity-MCP-Server（Streamable HTTP）",
    "autostart": {
      "command": "dotnet",
      "args": ["run", "--", "--port=22172", "--client-transport=streamableHttp"],
      "cwd": "C:/Users/PC/Documents/llm-server/Unity-MCP/Unity-MCP-Server",
      "ready_timeout_sec": 90
    }
  }
}
```

> **URL 路徑**：IvanMurzak 預設根路徑 `/` 即 MCP 端點；若 aicentral 連線失敗，可試 `http://localhost:22172` 或依 server 文件調整（勿與 Coplay 的 `/mcp` 混用）。

## 環境變數 autostart（免改 json）

在 `config/local.env.ps1` 或 shell 設定：

```powershell
$env:UNITY_MCP_SERVER_HOME = "C:\Users\PC\Documents\llm-server\Unity-MCP\Unity-MCP-Server"
# 可選：強制關閉 autostart
# $env:UNITY_MCP_AUTOSTART = "0"
```

`unity_servers.json` 使用 HTTP 且 port 未開時，Harness 會自動：

```text
dotnet run -- --port=<url 中的 port> --client-transport=streamableHttp
```

## Harness 行為

1. **`unity-mcp-harness` / `unity-mcp-list-tools` / `unity-mcp-ask`** 在註冊 MCP 前執行 port 檢查。
2. Port 已開 → 沿用外部程序，結束時**不**關閉。
3. Port 未開且有 autostart 設定 → Harness 啟動子程序，**整輪結束**後 terminate。
4. Port 未開且無 autostart → 拋出明確錯誤（含上述做法），避免裸 `ConnectionRefusedError`。
5. **`--no-autostart-mcp-server`**：只連已運行的 Server，不自動啟動。

## 與 stdio relay（舊 Coplay）的差異

| | IvanMurzak HTTP | Coplay stdio relay |
|--|-----------------|-------------------|
| 前置 | **dotnet Server 常駐** + Editor Plugin | Editor + relay_win.exe |
| 連線 | 固定 HTTP port | 每次 tool 可能新子行程 |
| 核准 | Plugin ↔ Server 配對 | Editor GUI 反覆 ALLOW |

遷移時請改 `unity_servers.json` 為 HTTP，並先確認 `unity-mcp-list-tools --json` 成功再跑建構。

## 參考

- [Unity-MCP-Server README](https://github.com/IvanMurzak/Unity-MCP/tree/main/Unity-MCP-Server)
- Harness：[NOTE.md](./NOTE.md)、[EXECUTE.md](./EXECUTE.md)
- 常駐 session 討論：[daemon.md](./daemon.md)（與 Server 生命週期互補）
