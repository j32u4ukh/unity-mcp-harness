# unity-mcp-harness

**Unity MCP Harness** 在 Unity Editor 上透過 [aicentral](../aicentral) 與 Coplay Unity MCP，依任務清單逐步完成建構。相對「發射後不管」的 Agent，Harness 目標是 **感知 → 行動 → 驗證 → 持久化** 的閉環，並以執行期 `task_list.yaml` 作為狀態來源（規格與路線圖見下方文件）。

| 檔案 | 角色 |
|------|------|
| `build_goals.yaml` | **建構藍圖**（意圖、DoD、粗粒度任務；人類/Cursor 維護） |
| `task_list.yaml` | **執行期 SSOT**（狀態、感知紀錄、驗證；Harness 執行時產生，規劃中） |

完整使用說明（腳本呼叫鏈、任務定義、設定檔分工）見 **[docs/README.md](docs/README.md)**。

### 規格與遷移

- **[docs/HARNESS.md](docs/HARNESS.md)** — 框架規格（藍圖 vs 執行期、Phase 1–4、Plan Normalize）
- **[docs/TO_HARNESS.md](docs/TO_HARNESS.md)** — 由現況到 Harness v1 的實作清單（可逐條勾選）

CLI 入口點為 `unity-mcp-harness`；旗標速查見 [docs/CLI.md](docs/CLI.md)。舊版 `unity-mcp-build` 已移除，請 `pip uninstall` 後重新 `pip install -e .`。

**外部工作區**（多專案、與引擎分離）見 **[docs/EXTERNAL_PROJECT.md](docs/EXTERNAL_PROJECT.md)** — 以 `unity-mcp-harness --init` 一鍵建立工作區。

---

## 快速開始

### 1. 安裝

```powershell
cd ..\aicentral
Copy-Item config\secret.yaml.example config\secret.yaml
# 建構預設 LLM 為 gemini-flash，請在 secret.yaml 填入 gemini.api_key
pip install -e ".[mcp]"

cd ..\unity-mcp-harness
pip install -e .
```

**外部工作區（推薦新專案）** — 不必在 harness repo 內放設定：

```powershell
mkdir C:\path\to\my-harness-workspace
cd C:\path\to\my-harness-workspace
unity-mcp-harness --init
# 編輯 config\secret.yaml、config\local.env.ps1
$env:UNITY_MCP_HOME = (Get-Location).Path
```

詳見 [docs/EXTERNAL_PROJECT.md](docs/EXTERNAL_PROJECT.md)。

### 2. Unity MCP（IvanMurzak）

預設使用 **[IvanMurzak/Unity-MCP](docs/IvanMurzak-Unity-MCP.md)**（Streamable HTTP + Harness autostart）。`unity_servers.json` 已含 `autostart`；Harness 在 port 未開時會自動 `dotnet run` Unity-MCP-Server。

```powershell
# 編輯 config\local.env.ps1：Unity 專案路徑 + UNITY_MCP_SERVER_HOME
. .\scripts\_env.ps1
unity-mcp-list-tools --json   # 應列出 kebab-case 工具（如 assets-find）
```

前置：

1. Unity 專案已安裝 **IvanMurzak Unity-MCP Plugin**，Plugin port 與 json 一致（預設 **22172**）
2. `config/local.env.ps1` 設好 `$UnityMcpServerHome`（或 json `autostart.cwd`）
3. Unity Editor **已開啟**且 Plugin 已連上 Server

手動常駐 Server（可選）：`.\scripts\start-unity-mcp-server.ps1`

**Coplay stdio relay（舊）** — 複製 `unity_servers.stdio.example.json`；見 [docs/NOTE.md](docs/NOTE.md)。

**Cursor IDE**：`%USERPROFILE%\.cursor\mcp.json` 可設 `"url": "http://localhost:22172"`；Harness CLI 讀工作區 `unity_servers.json`。

### 3. 多任務建構（主要流程）

```powershell
Copy-Item build_goals.example.yaml build_goals.yaml
# 編輯 tasks 列表
unity-mcp-harness
```

### 4. 其他指令

| 指令 | 說明 |
|------|------|
| `unity-mcp-harness` | 依 `task_list.yaml` 執行 Unity MCP 建構 |
| `unity-mcp-harness --goals build` | 藍圖 → `task_list`（只規劃，不跑 Unity） |
| `unity-mcp-harness --init [ROOT]` | 初始化外部工作區（scaffold 範本 + scripts） |
| `unity-mcp-chat` | **Unity 專案探索**（多輪 REPL；連線 MCP 查詢場景／資產現況） |
| `unity-mcp-ask "問題"` | **Unity 專案探索**（單次；`--probe` 使用預設唯讀探查 prompt） |
| `unity-mcp-list-tools` | 列出 MCP 工具（不呼叫 LLM） |

---

## 專案檔案一覽

| 檔案 | 用途 |
|------|------|
| `build_goals.yaml` | 建構藍圖 / 任務清單（自 example 複製） |
| `unity_servers.json` | Unity MCP 連線（自 example 複製；stdio 見 `unity_servers.stdio.example.json`） |
| `run_build.py` | `unity-mcp-build` 入口 |
| `build_workflow.py` | LangGraph 依序執行任務 |
| `tasks.py` | 載入 YAML、組 prompt |
| `unity_common.py` | 註冊 MCP、`Chat.with_mcp` |
| `unity_explore.py` | 探索 system prompt、MCP 驗證、啟動探查 |
| `config/unity_explore.yaml` | 探索行為設定（prompt、tool 輪數） |
| `unity_mcp_chat.py` / `unity_mcp_ask.py` / `unity_mcp_list_tools.py` | 互動與除錯 CLI |

### 打包成 exe（可選）

任務與 MCP 設定皆從 **YAML/JSON 執行期讀取**，修改 `build_goals.yaml` 等**不必**重新編譯。若希望 Unity MCP 只核准固定客戶端一次，可打包：

```powershell
pip install pyinstaller
.\scripts\build_exe.ps1
```

詳見 **[docs/EXE.md](docs/EXE.md)**。

---

## 文件

- [docs/CLI.md](docs/CLI.md) — CLI 旗標速查與 pip 重新安裝
- [docs/HARNESS.md](docs/HARNESS.md) — Harness 框架規格
- [docs/TO_HARNESS.md](docs/TO_HARNESS.md) — 遷移與實作清單
- [docs/README.md](docs/README.md) — 使用方式、呼叫鏈、任務定義
- [docs/BUILD.md](docs/BUILD.md) — 建構工作流補充
- [docs/NOTE.md](docs/NOTE.md) — 踩坑紀錄與自建 Agent 建議

---

## 測試

```powershell
pytest
```
