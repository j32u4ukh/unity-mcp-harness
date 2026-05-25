# Unity 建構工作流（LangGraph + aicentral-agent 技術棧）

> 完整使用說明（腳本、函式鏈、任務 YAML 欄位）請優先閱讀 **[README.md](./README.md)**。  
> 本頁為建構模式補充。

## 目的

在 `build_goals.yaml` 定義 Unity 遊戲的**建構目標與任務清單**，由 **LangGraph** 依序執行；每一步的 LLM 與 **Unity MCP** 工具呼叫經 **aicentral**（`Chat.with_mcp`），在 Editor 內實際修改場景。

## 三層分工

```
build_goals.yaml（本專案：任務定義）
        │
        ▼
build_workflow.py — LangGraph 狀態機（編排，與 aicentral-agent 同技術棧）
        │  每個節點：執行一則任務
        ▼
unity_common — Chat.with_mcp → aicentral → Unity MCP Server
        ▼
Unity Editor
```

| 層 | 專案 | 職責 |
|----|------|------|
| 任務 | unity-mcp `tasks.py` | 載入 YAML、組裝每步 prompt |
| 編排 | unity-mcp `build_workflow.py` | LangGraph 迴圈：任務 1 → 2 → … |
| 推理+工具 | aicentral | `complete` + MCP tool loop |
| 可選參考 | aicentral-agent | 單節點 / ReAct 範例；建構流在 unity-mcp 實作 |

## 快速開始

```powershell
# 1. Unity：依 unity_servers.json（stdio relay 或 http :8080，見 README §2）

# 2. aicentral
cd ..\aicentral
Copy-Item config\secret.yaml.example config\secret.yaml
pip install -e ".[mcp]"

# 3. unity-mcp
cd ..\unity-mcp
pip install -e ".[dev]"
Copy-Item build_goals.example.yaml build_goals.yaml
# 編輯 build_goals.yaml 任務

# 4. 執行（需模型支援 function calling）
unity-mcp-build

# 只預覽任務
unity-mcp-build --dry-run
```

## 任務檔格式

見 `build_goals.example.yaml`：

| 欄位 | 說明 |
|------|------|
| `project` | 整體專案描述（寫入每步 prompt） |
| `model` | 可選，覆寫 aicentral 預設模型 |
| `max_tool_rounds` | 單任務內 MCP tool loop 上限 |
| `mcp_servers` | Unity MCP 名稱列表（對應 unity_servers.json） |
| `system_context` | 所有任務共用背景 |
| `tasks[].id` | 唯一識別 |
| `tasks[].title` | 簡短標題 |
| `tasks[].prompt` | 交給 LLM 的具體指示 |
| `tasks[].enabled` | 預設 true；false 則跳過 |
| `tasks[].mcp_servers` | 可選，覆寫該任務的 MCP server |

環境變數：`UNITY_BUILD_GOALS` 指向任務檔路徑。

## 執行行為

- 使用**同一** `Chat` 工作階段，`include_tool_messages_in_history=True`，後續任務可參考先前 MCP 操作。
- 每步 prompt 會附上**已完成任務**的摘要。
- 預設**任務失敗即停止**；`unity-mcp-build --continue-on-error` 可繼續。
- 非串流 MCP loop（與 aicentral 限制一致）。

## Python API

```python
from tasks import resolve_build_plan
from build_workflow import run_build_plan

plan = resolve_build_plan()
results = run_build_plan(plan)
for r in results:
    print(r.id, r.success, r.reply[:200])
```

## 與 aicentral-agent 的差異

| | aicentral-agent | unity-mcp 建構流 |
|--|-----------------|------------------|
| 編排 | 通用 LangGraph / ReAct | **任務清單**驅動的順序圖 |
| 工具 | 自訂 `@tool` | **Unity MCP** |
| LLM 適配 | `ChatAicentral` | `Chat.with_mcp` |

若要「先由 ChatAicentral 規劃任務再執行」，可在消費方先呼叫 aicentral-agent 產生 YAML，再執行 `unity-mcp-build`。
