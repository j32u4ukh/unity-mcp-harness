# unity-mcp 使用說明

> 安裝與依賴見專案根目錄 [README.md](../README.md)。  
> 建構工作流補充見 [BUILD.md](./BUILD.md)。

---

## 這個專案做什麼

**unity-mcp** 讓你用 **aicentral** 呼叫 **Unity MCP Server**，在 Unity Editor 裡透過 AI 操作場景與資源。

主要有兩種用法：

| 模式 | 適合情境 | 入口指令 |
|------|----------|----------|
| 多任務建構（推薦） | 依清單逐步完成場景搭建 | `unity-mcp-build` |
| 互動對話 | 手動一問一答、試工具 | `unity-mcp-chat` / `unity-mcp-ask` |

多任務建構會用 **LangGraph** 依 `build_goals.yaml` 的順序執行；每一步由 **LLM + Unity MCP 工具** 實際改 Editor。

---

## 前置條件

1. Unity 專案已開啟，且 MCP 已就緒（依 `unity_servers.json` 的 **transport**）：
   - **stdio（預設）**：`C:\Users\PC\.unity\relay\relay_win.exe --mcp`；Editor 已連上 relay（**不必**開 `localhost:8080`）
   - **http（可選）**：Editor 內啟動 HTTP MCP（例如 `http://localhost:8080/mcp`）
2. [aicentral](../../aicentral) 已設定 LLM（`config/aicentral.yaml` + `config/secret.yaml`）。
3. 模型需支援 **function calling**（MCP tool loop 必要）。

```powershell
cd ..\aicentral
Copy-Item config\secret.yaml.example config\secret.yaml
pip install -e ".[mcp]"

cd ..\unity-mcp
pip install -e .
```

---

## 一、多任務建構：從腳本到 Unity 的完整鏈路

### 你要執行的指令

```powershell
Copy-Item build_goals.example.yaml build_goals.yaml
# 編輯 build_goals.yaml
unity-mcp-build
```

對應安裝後的 entry point：`run_build.py` → `main()`。

### 呼叫鏈（誰叫誰）

下面是一次 `unity-mcp-build` 執行時，由外到內的呼叫順序：

```
unity-mcp-build
└─ run_build.py :: main()
   ├─ require_aicentral_config()          # 檢查 aicentral secret.yaml
   ├─ resolve_build_plan()              # tasks.py — 讀 build_goals.yaml
   ├─ resolve_server_specs()            # unity_common — 讀 unity_servers.json 等
   ├─ register_unity_servers()          # unity_common — 執行期註冊 MCP（不寫 aicentral.yaml）
   └─ run_build_plan()                  # workflow.py
      └─ build_sequential_workflow()   # 編譯 LangGraph
         └─ graph.invoke(initial_state)
            └─ [迴圈] 節點 run_task（每個任務一次）
               └─ _run_single_task()
                  ├─ format_task_prompt()     # tasks.py — 組本任務提示（含已完成摘要）
                  └─ chat.ask(prompt)         # 或 ask_unity()（任務自訂 mcp_servers 時）
                     └─ Chat.with_mcp → aicentral.complete(..., mcp_servers=...)
                        └─ complete_with_mcp_loop()   # aicentral/mcp/orchestrator.py
                           ├─ MCPManager.list_tools()   # 向 Unity MCP 列工具
                           ├─ invoke_resolved() + tools  # 問 LLM（aicentral 路由）
                           ├─ 模型回傳 tool_calls
                           ├─ MCPManager.call_tool()    # 呼叫 Unity MCP 工具改 Editor
                           └─ 重複直到最終文字或達 max_tool_rounds
```

### LangGraph 怎麼「逐步」執行多項任務

圖結構（`workflow.py`）：

```
START → run_task →（條件）→ run_task → … → END
              ↑__________________|
```

| 步驟 | 程式位置 | 行為 |
|------|----------|------|
| 1 | `run_build_plan` | `task_index=0`，`results=[]` |
| 2 | 節點 `run_task` | 取 `plan.enabled_tasks()[task_index]`，執行該任務 |
| 3 | `_route_after_task` | 若還有任務且上一個成功 → 再進 `run_task`；否則 `END` |
| 4 | 重複 2–3 | 直到任務做完或失敗停止 |

同一輪建構共用一個 `Chat` 實例（`include_tool_messages_in_history=True`），後面的任務能看到前面任務的 MCP 操作歷史。

### 單一任務內部（LLM 與 Unity 工具）

一則任務不是只問 LLM 一句話，而是 **MCP tool loop**（由 aicentral 負責）：

1. 向 Unity MCP **列出工具**（例如建立物件、改 Hierarchy、執行選單等，依你的 MCP 實作而定）。
2. LLM 決定要呼叫哪些工具、參數為何。
3. **call_tool** 在 Unity Editor 執行。
4. 把工具結果塞回對話，再問 LLM，直到產出最終說明文字或達 `max_tool_rounds`。

因此 `build_goals.yaml` 的 `prompt` 應寫成「要做什麼」，不必手動指定工具名稱；模型會從 MCP 工具列表中選擇。

---

## 二、多項任務要怎麼定義

### 檔案位置與優先序

| 優先序 | 來源 |
|--------|------|
| 1 | `unity-mcp-build -g 路徑` |
| 2 | 環境變數 `UNITY_BUILD_GOALS` |
| 3 | 本目錄 `build_goals.yaml`（建議，已 gitignore） |
| 4 | `build_goals.example.yaml`（範本） |

### 完整 YAML 結構

```yaml
# 整份建構的標題（會寫進每步 prompt）
project: "我的遊戲 — 第一關場景"

# 可選：覆寫 aicentral 預設模型（否則用 config/aicentral.yaml 的 defaults.model）
# model: ollama/gemma4:e2b

# 單一任務內，LLM↔MCP 工具往返次數上限
max_tool_rounds: 12

# 對應 unity_servers.json 裡註冊的名稱（預設 ["unity"]）
mcp_servers:
  - unity

# 可選：整份建構的總目標（會注入每步 prompt）
goal: |
  建立可遊玩的最小場景。

# 可選：完成定義清單（每步可見；validate_scene 會要求逐項核對）
definition_of_done:
  - Scene 已保存
  - 主要物件已建立

# 可選：執行策略（goal_driven、優先順序等）
execution_strategy:
  mode: goal_driven
  priorities: [correctness]

# 可選：Agent 憲法（規則、工具使用、禁止事項）
system_context: |
  這是 2.5D 平台遊戲的第一關。
  不要刪除名為 GameManager 的物件。

# 任務列表：會依陣列順序執行
tasks:
  - id: 唯一識別
    title: 顯示用短標題
    objective: |
      本步驟要達成的結果（可選，會併入 prompt）
    prompt: |
      給 LLM 的具體指示（繁體中文即可）。
      說明要在 Unity 裡完成什麼、完成後回報什麼。
    enabled: true          # 可選，預設 true；false 則跳過
    # mcp_servers: [unity_alt]  # 可選，覆寫此任務的 MCP server
```

### 任務欄位說明

| 欄位 | 必填 | 說明 |
|------|------|------|
| `project` | 否 | 專案顯示名稱 |
| `goal` | 否 | 總體目標（`tasks.format_task_prompt` 注入） |
| `definition_of_done` | 否 | 完成定義清單；`validate_scene` 任務會強調逐項核對 |
| `execution_strategy` | 否 | 執行策略物件（mode / priorities / behavior） |
| `system_context` | 否 | Agent 憲法／共用規則 |
| `max_tool_rounds` | 否 | 每任務 MCP 往返上限（預設 10） |
| `mcp_servers` | 否 | 對應 `unity_servers.json` 的 server 名稱 |
| `model` | 否 | 覆寫 aicentral 對話模型 |

任務（`tasks[]`）：

| 欄位 | 必填 | 說明 |
|------|------|------|
| `id` | 是 | 英文識別，用於日誌與結果；建議 `snake_case` |
| `title` | 是 | 終端機顯示用短標題 |
| `objective` | 否 | 本任務目標摘要（併入 prompt） |
| `prompt` | 是 | 該步驟對 LLM 的指令；寫清楚目標與驗收方式 |
| `enabled` | 否 | `false` 時跳過（方便暫時關閉某步） |
| `mcp_servers` | 否 | 該任務改用其他 MCP 實例；未填則用頂層 `mcp_servers` 且共用 Chat 歷史 |

### 撰寫任務的建議

1. **一步一事**：每個 `id` 只做一類事（例如「建地面」「建玩家」「打光」），不要一個 prompt 塞整關。
2. **依賴順序**：會依賴前一步結果的任務放在後面；系統會把已完成任務摘要附在 prompt 裡。
3. **可驗收**：prompt 結尾要求「簡述你建立了什麼、物件名稱與位置」，方便人工檢查。
4. **先偵查再動手**：第一個任務可先 `inspect_scene` 列出 Hierarchy，減少模型盲目操作。

### 範例（節錄）

見 [build_goals.example.yaml](../build_goals.example.yaml)：

- `inspect_scene` — 只讀、了解現狀  
- `add_ground` — 建立 Plane  
- `add_player_cube` — 建立 Cube  
- `add_light` — 加 Directional Light  

### 執行選項

```powershell
unity-mcp-build --dry-run              # 只列將執行的任務
unity-mcp-build --continue-on-error    # 某任務失敗仍繼續
unity-mcp-build --json                 # 結果輸出 JSON
unity-mcp-build -g my_plan.yaml -c unity_servers.json
```

---

## 三、其他腳本與函式對照

### 腳本總表

| 指令 / 腳本 | 用途 |
|-------------|------|
| `unity-mcp-build` | `run_build.py` — 依任務清單順序建構 |
| `unity-mcp-chat` | `chat.py` — 多輪互動 REPL |
| `unity-mcp-ask` | `ask.py` — 單次提問 |
| `unity-mcp-list-tools` | `list_tools.py` — 只列 MCP 工具，不呼叫 LLM |

### unity-mcp-chat / unity-mcp-ask

```
chat.py / ask.py
└─ create_unity_chat() 或 ask_unity()     # unity_common.py
   └─ register_unity_servers()
   └─ Chat.with_mcp(...).ask(問題)
      └─ 同上 MCP tool loop（單輪對話，無 LangGraph）
```

適合除錯 MCP 連線、試單一指令，**不會**讀 `build_goals.yaml`。

### unity-mcp-list-tools

```
list_tools.py
└─ list_unity_tools()                     # unity_common.py
   └─ register_unity_servers()
   └─ MCPManager.list_tools(server)       # aicentral
```

只確認 Unity MCP 連得上、有哪些工具名稱，不消耗 LLM。

---

## 四、設定檔分工

| 檔案 | 管什麼 | 誰讀 |
|------|--------|------|
| `aicentral/config/aicentral.yaml` | LLM 模型、路由、fallback | aicentral |
| `aicentral/config/secret.yaml` | API 金鑰 | aicentral |
| `unity_servers.json` | Unity MCP 連線（URL / stdio） | `unity_common` |
| `build_goals.yaml` | 建構任務清單 | `tasks.py` |

Unity MCP **不**寫進 `aicentral.yaml`；一律在 unity-mcp 執行期 `register_unity_servers()`。

---

## 五、Python API（不經 CLI）

```python
from tasks import resolve_build_plan
from workflow import run_build_plan

plan = resolve_build_plan()  # 讀 build_goals.yaml
results = run_build_plan(plan)

for r in results:
    print(r.id, r.success, r.reply[:200] if r.reply else r.error)
```

---

## 六、與 aicentral-agent 的關係

| 專案 | 角色 |
|------|------|
| **aicentral** | LLM + MCP tool loop 能力庫 |
| **aicentral-agent** | 通用 LangGraph / ReAct 範例（`ChatAicentral`） |
| **unity-mcp** | Unity 專用：任務 YAML + 順序建構 + `Chat.with_mcp` |

建構工作流的 LangGraph **實作在 unity-mcp**（`workflow.py`），技術棧與 aicentral-agent 相同，但任務來自 `build_goals.yaml` 而非通用 ReAct。

---

## 七、常見問題

**Q：任務 2 不知道任務 1 做了什麼？**  
A：確認未對單獨任務設 `mcp_servers` 覆寫（覆寫會用新的 `ask_unity`、不共用 Chat 歷史）。預設共用 `Chat` 且 `include_tool_messages_in_history=True`。

**Q：MCP 連線失敗？**  
A：先 `unity-mcp-list-tools`；檢查 Unity 外掛與 `unity_servers.json` / `UNITY_MCP_URL`。

**Q：模型不呼叫工具？**  
A：換支援 function calling 的模型；加大 `max_tool_rounds`；在 prompt 明確寫「請使用 Unity MCP 工具執行」。

**Q：想從程式動態產生任務？**  
A：可組 `BuildPlan` / `BuildTask` 物件（`tasks.py`）後傳入 `run_build_plan(plan)`，不必經 YAML 檔。
