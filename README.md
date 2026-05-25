# unity-mcp

透過 [aicentral](../aicentral) 呼叫 **Unity MCP Server**，並可依 **任務清單** 在 Unity Editor 內逐步完成建構。

完整使用說明（腳本呼叫鏈、任務定義、設定檔分工）見：

**[docs/README.md](docs/README.md)**

---

## 快速開始

### 1. 安裝

```powershell
cd ..\aicentral
Copy-Item config\secret.yaml.example config\secret.yaml
# 建構預設 LLM 為 gemini-flash，請在 secret.yaml 填入 gemini.api_key
pip install -e ".[mcp]"

cd ..\unity-mcp
pip install -e .
```

### 2. Unity MCP

複製連線設定到 **`unity_servers.json`**（已 gitignore），檔名須與 `build_goals.yaml` 的 `mcp_servers` 一致（預設 `unity`）。

**stdio + relay（本專案預設）** — 複製 `unity_servers.stdio.example.json` 或使用下列內容寫入 `unity_servers.json`：

```json
{
  "unity": {
    "transport": "stdio",
    "command": "C:\\Users\\PC\\.unity\\relay\\relay_win.exe",
    "args": ["--mcp"],
    "auth_type": "none"
  }
}
```

前置：Unity Editor **已開啟**，MCP 外掛已連上 relay（Named Pipe）。驗證：`unity-mcp-list-tools --json`。

**HTTP（可選）** — 複製 `unity_servers.example.json`；須在 Unity 內啟動 MCP Server（例如 `http://localhost:8080/mcp`）。Cursor 若用 HTTP 可參考 [docs/cursor-mcp.http.example.json](docs/cursor-mcp.http.example.json)。

**Cursor IDE**：`%USERPROFILE%\.cursor\mcp.json` 可與上列 stdio（`command`/`args`）或 HTTP（`url`）擇一；**unity-mcp CLI** 一律讀本專案 `unity_servers.json`（aicentral 格式，含 `transport`）。

### 3. 多任務建構（主要流程）

```powershell
Copy-Item build_goals.example.yaml build_goals.yaml
# 編輯 tasks 列表
unity-mcp-build
```

### 4. 其他指令

| 指令 | 說明 |
|------|------|
| `unity-mcp-build` | 依 `build_goals.yaml` 順序執行任務 |
| `unity-mcp-chat` | 多輪對話 REPL |
| `unity-mcp-ask "問題"` | 單次提問 |
| `unity-mcp-list-tools` | 列出 MCP 工具（不呼叫 LLM） |

---

## 專案檔案一覽

| 檔案 | 用途 |
|------|------|
| `build_goals.yaml` | 建構任務清單（自 example 複製） |
| `unity_servers.json` | Unity MCP 連線（自 example 複製；stdio 見 `unity_servers.stdio.example.json`） |
| `run_build.py` | `unity-mcp-build` 入口 |
| `build_workflow.py` | LangGraph 依序執行任務 |
| `tasks.py` | 載入 YAML、組 prompt |
| `unity_common.py` | 註冊 MCP、`Chat.with_mcp` |
| `chat.py` / `ask.py` / `list_tools.py` | 互動與除錯 CLI |

### 打包成 exe（可選）

任務與 MCP 設定皆從 **YAML/JSON 執行期讀取**，修改 `build_goals.yaml` 等**不必**重新編譯。若希望 Unity MCP 只核准固定客戶端一次，可打包：

```powershell
pip install pyinstaller
.\scripts\build_exe.ps1
```

詳見 **[docs/EXE.md](docs/EXE.md)**。

---

## 文件

- [docs/README.md](docs/README.md) — 使用方式、呼叫鏈、任務定義
- [docs/BUILD.md](docs/BUILD.md) — 建構工作流補充
- [docs/NOTE.md](docs/NOTE.md) — 踩坑紀錄與自建 Agent 建議

---

## 測試

```powershell
pytest
```
