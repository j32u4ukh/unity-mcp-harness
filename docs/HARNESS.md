# Unity MCP Harness 框架規格（Framework Specification）

本文件有兩個讀者與用途：

1. **對內（Cursor / 維護者）**：定義 `unity-mcp-harness` 的目標架構（閉環控制、動態任務注入、狀態持久化），指導重構與模組邊界。
2. **對外（執行中的 Agent）**：作為 **Runtime Guide**，規定呼叫 Unity MCP 時必須遵循「感知 → 決策/行動 → 驗證 → 持久化」，不得僅依文字幻覺宣告完成。

---

## 0. 現況基線與 Harness 差異

專案已由 `unity-mcp` 更名為 `unity-mcp-harness`，**執行鏈路仍為「Agent + Unity MCP」**；Harness **規範與程式化強制**多數尚未落地。

### 0.1 目前已具備（Agent + MCP 層）

| 元件 | 路徑 / 指令 | 職責 |
|------|-------------|------|
| 建構意圖 | `build_goals.yaml` | 靜態任務清單、`goal`、`definition_of_done`、`system_context`、各任務 `prompt` |
| 任務載入 | `tasks.py` | 解析 YAML、組裝每步 LLM prompt（含已完成任務摘要） |
| 編排 | `build_workflow.py` | LangGraph **單次行程**依序執行各任務 |
| MCP + LLM | `unity_common.py` + `harness/mcp_runner.py` → aicentral `Chat.with_mcp` | 註冊 `unity_servers.json`、tool loop |
| 入口 | `run_build.py` / `unity-mcp-build` | CLI；可打包為 `unity-mcp-build.exe` |
| Unity 連線 | Coplay **Unity MCP**（stdio `relay_win.exe` 或 HTTP） | 實際 Editor 工具，如 `Unity_ListResources`、`Unity_RunCommand` 等 |

**現有冪等性**：主要靠 `build_goals.yaml` 內 `system_context` / 各任務 `prompt` 的**文字約束**（「先檢查、已存在則跳過」），以及 `task_reply_indicates_failure` 等**啟發式**失敗判斷。  
**尚未具備**：藍圖 LLM 規範化（見 §2.1）、結構化 Phase 1–3 紀錄、`task_list.yaml` 落盤、框架級斷點續傳、執行期動態子任務寫回隊列。

**規範與撰寫的落差**：HARNESS 要求每步「先讀現場再寫入、寫後再驗證」，但 `build_goals.yaml` 由人類/Cursor 撰寫時**無法強制**每條 `prompt` 都符合。因此 Harness 在進入 Unity MCP 執行迴圈前，須先對藍圖做一次 **Plan Normalize（規劃期規範化）** LLM 回合（§2.1），再 bootstrap 至 `task_list.yaml`。

### 0.2 Harness 目標（相對現況要補上的）

| 能力 | 現況 | Harness 目標 |
|------|------|----------------|
| 藍圖任務定義 | 完全依賴 YAML 撰寫品質 | **`core/pipeline/plan_normalize`**（LLM 或 passthrough）補齊 Harness 欄位、可拆分子任務 |
| 藍圖 ↔ 執行隊列 | 直接 `tasks.py` 讀 `build_goals` | **`bootstrap`** → `task_list`；`run_build --write-back-goals` 可寫回藍圖 |
| 執行期 SSOT | 僅記憶體內 `TaskResult` | `task_list.yaml` 即時更新 |
| 操作前感知 | Prompt 要求 Agent 自行讀取 | Phase 1 狀態寫入 `pipeline_records.actual_before` |
| 操作後驗證 | Prompt + 文字回覆 | Phase 3 比對 `actual_after` vs 預期，寫入 `verification` |
| 規劃期擴充任務 | 無 | 3 條粗任務可規範化為 N 條（§2.1），再進執行隊列 |
| 執行期動態子任務 | Prompt 建議 | 寫入 `task_list.yaml` 並插隊執行（§3 Phase 2C） |
| 斷點續傳 | `enabled: false` 或重跑 | 跳過 `status: completed`，對下一項重做 Phase 1 |
| 工具分層 | 混用 Coplay 通用工具 | 明確 Read / Write 慣例與 Token 過濾（見 §5） |

詳細實作步驟見 [TO_HARNESS.md](./TO_HARNESS.md)。

---

## 1. 核心設計哲學

傳統腳本或「發射後不管」的 Agent 在 Unity Editor 中易產生幻覺與髒場景。Harness 核心原則：**無感知，不行動**。

1. **狀態冪等性**：變更前先確認現場；已達標則標記完成，不重複寫入。
2. **動態依賴解析**：缺組件/資源時，注入高優先級前置子任務，而非直接失敗結束。
3. **驗證與斷言**：寫入操作後必須二次讀取，比對實際與預期。
4. **狀態持久化與斷點續傳**：任務階段、感知與驗證結果落盤 YAML，程序可隨時重啟接續。

---

## 2. 雙檔案分工：`build_goals.yaml` vs `task_list.yaml`

避免與現有流程衝突，兩份 YAML 職責分離：

| 檔案 | 角色 | 誰寫入 | 生命週期 |
|------|------|--------|----------|
| **`build_goals.yaml`** | **建構藍圖**（意圖、DoD、策略、**粗粒度**任務模板） | 人類 / Cursor；Harness **可選寫回** | 版本管理、可審閱；改檔後**不必**重編 exe |
| **`task_list.yaml`** | **執行期 SSOT**（規範化後任務、狀態、感知、操作紀錄、驗證、動態注入） | Harness `core/pipeline` + Agent | 每次執行期 Phase 4 更新；重啟時 resume |

人類撰寫的 `build_goals.yaml` 允許**意圖導向、條目較少**（例如僅 3 個大任務）；Harness 不保證其 `prompt` 已含「先讀後寫、寫後驗證」等句式——那是 **Plan Normalize** 的職責，而非維護者的義務。

### 2.1 Plan Normalize（規劃期規範化，執行 Unity MCP 之前）

在 `tasks.load_build_goals()` 之後、`bootstrap` / 第一個 `UnityMCPRunner.ask()` **之前**，框架應發起 **一次（或固定輪次）純規劃 LLM 呼叫**（預設**不**連 Unity MCP，以降低核准與 token 成本；可選 `--plan-with-mcp` 讀專案目錄結構輔助拆任務）。

**輸入**：

- `build_goals.yaml` 全文（`goal`、`definition_of_done`、`system_context`、`tasks[]`）；
- [HARNESS.md](./HARNESS.md) 任務契約摘要（§2.2、§3、§6）；
- 可選：上一輪 `task_list.yaml` 的 `plan_revision`（避免重複拆分的雜訊）。

**輸出（結構化，建議 YAML/JSON schema）**：

- **規範化後任務列表** `normalized_tasks[]`（數量可 ≠ 原始條數）；
- 每任務補齊：`id`、`description`、`priority`、`target` / `expected` 占位、`harness.pre_read` / `harness.post_read` 提示；
- 每任務 `prompt` 內嵌執行期 CoT（至少明示：本步須 Phase 1 讀取 → Phase 2 寫入 → Phase 3 再讀驗證）；
- `plan_changelog`：相對原藍圖的拆分/合併/改寫說明。

**典型變換**（藍圖 3 條 → 執行隊列 6+ 條）：

| 原藍圖（粗） | 規範化可能產出 |
|-------------|----------------|
| 「建立 2D 場景」 | `create_2d_scene`、`ensure_2d_camera`、`ensure_global_light_2d` |
| 「建立紅色方塊」 | `create_red_square_go`、`set_sprite_red` |
| 「驗證場景」 | `validate_2d_scene`（含 `expected` 與唯讀驗證腳本提示） |

**寫回 `build_goals.yaml`（可選、建議需旗標）**：

| 模式 | 行為 |
|------|------|
| 預設 | 僅將 `normalized_tasks` 寫入 **`task_list.yaml`**（bootstrap），**不**改藍圖檔 |
| `--write-back-goals` | 將規範化後的 `tasks`（及必要時 `plan_revision` 註解）**合併寫回** `build_goals.yaml`，供版控與人工 diff |
| `--write-back-goals --backup` | 寫回前複製 `build_goals.yaml.bak` |

寫回目的：讓下次人類打開藍圖即為「已規範化」版本，減少重複 LLM 規劃成本；**執行期 SSOT 仍以 `task_list.yaml` 為準**，避免與 `completed` 紀錄衝突時應以 sync 規則（§8 / TO_HARNESS 階段 8）處理。

**與執行期動態注入的區別**：

| | Plan Normalize（規劃期） | Runtime Inject（執行期 §3.2C） |
|--|------------------------|--------------------------------|
| 時機 | 啟動後、首個 Unity 工具前 | 某任務 Phase 1 發現缺組件 |
| 觸發 | 藍圖不完整 / prompt 不合規 | MCP 讀取結果 |
| 寫入 | `task_list` 初始隊列；可選寫回 `build_goals` | 僅 `task_list` 插隊 |
| LLM | 專用規劃 prompt（無工具或唯讀） | 執行 Agent + MCP |

### 2.2 任務定義契約（Plan Normalize 必須滿足）

規範化後的每一任務至少應具備（寫入 `task_list`；寫回藍圖時對應 `tasks[]` 欄位）：

1. **穩定 `id`**（snake_case，與 DoD 可追溯）。
2. **`prompt`** 含：目標物件/路徑、冪等語句（已存在則跳過）、**禁止**違反 `system_context` 的操作（如 2D 禁用 MeshRenderer）。
3. **`harness` 區塊（可選但建議）**：`pre_read`（建議唯讀 MCP/C#）、`post_read`（驗證讀取）、`expected` 摘要。
4. **`priority`**：數字越小越先執行（或專案約定一致即可）。
5. **單步可驗證**：一任務對應一個可獨立 `verification` 的結果，避免「巨型 prompt」混多個 DoD。

Normalize **不得**取代執行期 Phase 1：即使 prompt 已寫「先讀取」，進入 Unity 後仍須依現場 MCP 更新 `actual_before`（現場可能與上次規劃時不同）。

### 2.3 啟動流程（目標）

```
build_goals.yaml（人類粗藍圖）
        │
        ▼
  Plan Normalize（LLM，§2.1）
        │
        ├─[可選]──> 寫回 build_goals.yaml
        │
        ▼
  bootstrap ──> task_list.yaml（pending）
        │
        ▼
  unity-mcp-build：僅驅動 task_list 未完成項（執行期 Phase 1–4）
```

1. 載入 `build_goals.yaml`。
2. **Plan Normalize** → 得到 `normalized_tasks`（可能 3→N）。
3. 若無 `task_list.yaml` 或 `--replan`：bootstrap 寫入 `task_list.yaml`（`source_plan`、`plan_revision`）。
4. 執行迴圈只讀 `task_list.yaml`；人類改藍圖後可 `sync-plan` / `--replan`（見 TO_HARNESS 階段 8）。

---

## 3. 閉環控制流水線

分兩層：**規劃期**（§2.1，無 Unity 現場）與 **執行期**（下列四階段，需 MCP）。

### 3.0 執行期四階段（Per-Task Runtime）

Agent 與框架皆應圍繞下列流水線；**現階段由 Prompt 引導，中長期由 `core/pipeline` 強制與落盤**。  
各任務的 `prompt` 應已在 Plan Normalize 中嵌入本節要點；執行時仍須真實跑 MCP，不可只重複文字。

```
+------------------+   狀態已滿足（冪等）    +------------------+
| Phase 1: 感知     |---------------------->| Phase 4: 持久化   |
| Pre-Perception   |                       | Persistence      |
+------------------+                       +------------------+
        | 狀態未滿足                                    ^
        v                                             |
+------------------+   缺先決條件                     |
| Phase 2: 決策     |-----------> 動態注入子任務 --------+
| Decision / Act   |         （寫入 task_list.yaml）
+------------------+
        | 已執行寫入
        v
+------------------+
| Phase 3: 驗證     |---- 通過 ---> Phase 4
| Post-Assertion   |---- 失敗 ---> 分析 / Undo（可選）/ failed
+------------------+
```

### Phase 1：操作前感知（Pre-Perception）

- **Agent**：修改前先呼叫**讀取類** MCP（見 §5.2）。
- **框架**：將結果寫入 `pipeline_records.actual_before`（組件列表、關鍵屬性、路徑）。
- **上下文**：`tasks.format_task_prompt` / pipeline 將 `actual_before` 摘要注入本步 prompt。

### Phase 2：決策與動態規劃（Decision / Act）

- **分支 A — 冪等跳過**：`actual_before` 已符合預期 → `status: completed`，進 Phase 4。
- **分支 B — 常規執行**：條件具備 → 呼叫**寫入類** MCP（建立物件、改屬性、`Unity_RunCommand` 等）。
- **分支 C — 動態注入**：缺先決條件（如 2D 專案缺 `SpriteRenderer`）→ 在 `task_list.yaml` **插入**前置任務（較高優先序），紀錄 `Dynamic_Task_Injection`，先執行子任務再回到主任務。

### Phase 3：操作後驗證（Post-Assertion）

- **禁止**僅因 API 已呼叫即視為成功。
- 再次讀取現場 → `pipeline_records.actual_after`。
- 與預期比對：`verification: verified | failed | pending`。
- 連續失敗可觸發 Undo（§6，待 Unity 側支援）。

### Phase 4：持久化（Persistence）

- 更新 `task_list.yaml`：`status`、`last_updated`、`pipeline_records`、`verification`。
- 重啟時：跳過 `completed`，對下一個 `pending` / `in_progress` **重新執行 Phase 1**（現場可能已變）。

---

## 4. `task_list.yaml` 結構規範（執行期 SSOT）

路徑預設：專案根目錄 `task_list.yaml`（與 `build_goals.yaml` 並存，gitignore 可選）。

```yaml
project_name: "PlanetaryMalignancy"
harness_version: 1
last_updated: "2026-05-25T22:00:00Z"
current_lifecycle_phase: "Scene_Verification"
source_plan: "build_goals.yaml"   # bootstrap 來源
plan_revision: 2                  # Plan Normalize 次數或內容 hash
plan_normalized_at: "2026-05-25T21:50:00Z"

tasks:
  - id: "create_2d_scene"
    description: "建立並啟用 Example2DScene"
    status: "completed"            # pending | in_progress | completed | failed | skipped
    priority: 10
    target:
      game_object: null
      scene_path: "Assets/_Scenes/Example2DScene.unity"
    expected:
      properties: {}               # 本任務完成後應滿足的斷言（可選）
    pipeline_records:
      actual_before: {}
      operations_executed:
        - timestamp: "2026-05-25T21:58:00Z"
          action: "MCP_Read"         # 或 Unity_ListResources 等實際工具名
          tool: "unity__Unity_ListResources"
          summary: "..."
      actual_after: {}
    verification: "verified"       # verified | failed | pending | skipped_by_idempotent
    injected_by: null                # 執行期動態注入填父任務 id；規劃期拆分則為 null，見 plan_changelog
    plan_source_id: "create_scene"   # 可選：對應藍圖粗任務 id，便於寫回 build_goals
```

**與 `build_goals.yaml` 任務 id**：規劃期拆分後 `id` 可能為子任務（如 `ensure_2d_camera`）；`plan_source_id` 保留與藍圖粗項對照。寫回藍圖時以 `plan_changelog` 說明 3→N 映射。

---

## 5. MCP 與工具慣例（Coplay Unity MCP）

Harness **不取代** Coplay Unity MCP Server；而是在其工具之上建立 **Read / Write 行為契約**。

### 5.1 連線（本 repo 現況）

- 設定：`unity_servers.json`（stdio `relay_win.exe` 或 HTTP）。
- LLM：`aicentral` + `aicentral-agent`，經 `Chat.with_mcp` 多輪 tool loop。
- 注意：stdio 下每次 `call_tool` 可能新建 relay 子行程；Editor 需 **Auto-approve** 或固定客戶端（見 `docs/NOTE.md`、`docs/EXE.md`）。

### 5.2 讀取類（Phase 1 / 3）— 現有工具映射

優先使用列表/查詢類工具，避免一次拉取整個場景：

| 用途 | 現有 Coplay 工具（示例） | Harness 要求 |
|------|-------------------------|----------------|
| 資源/路徑是否存在 | `Unity_ListResources`、場景相關 list | 回傳寫入 `actual_before` / `actual_after` |
| 物件/組件狀態 | `Unity_RunCommand`（唯讀 C#）、Inspector 類工具（若有） | 只讀必要屬性；**禁止**順便修改 |
| 精簡屬性 | 待封裝：`filters` 參數約定 | 只取本任務相關欄位（如 `SpriteRenderer.color`） |

### 5.3 寫入類（Phase 2）— 現有工具映射

| 用途 | 現有 Coplay 工具（示例） | Harness 要求 |
|------|-------------------------|----------------|
| 建立場景/資料夾 | 場景與 Asset 管理工具 | 記錄於 `operations_executed` |
| 建立 GO / 掛組件 | `Unity_ManageGameObject` 等 | 2D 專案禁止誤用 3D Mesh 路徑（見 `build_goals.yaml`） |
| 改屬性 / 執行腳本 | `Unity_RunCommand` | 執行後**必須**進入 Phase 3 |

未來可在 `core/pipeline/tool_adapter.py` 將工具名統一包裝為 `harness_read` / `harness_write`，便於紀錄與測試。

---

## 6. 給執行中 Agent 的思考模型（CoT）

1. **接到任務**  
   - 錯：立刻 `set_color`。  
   - 對：先讀現場 → 寫入/更新 `actual_before` → 再決定跳過或修改。

2. **缺少組件**  
   - 錯：回報錯誤結束。  
   - 對：在 `task_list.yaml` 注入子任務 → 執行 → 回到主任務。

3. **執行修改後**  
   - 錯：「已呼叫 API，完成。」  
   - 對：再讀一次 → 比對 → `verification: verified` → Phase 4 落盤。

Agent 仍透過 `UnityMCPRunner.ask()` 驅動，但 prompt 應包含（由框架注入）：

- 當前任務的 `pipeline_records` 摘要；
- 本步必須完成的 Phase（例如「本輪至少一次讀取 + 一次寫後讀」）；
- `build_goals.yaml` 中的 2D/路徑等**專案憲法**。

---

## 7. 目標專案結構（相對現有扁平模組）

現況為根目錄 `tasks.py`、`build_workflow.py`、`unity_common.py` 等。Harness 演進目標：

```
unity-mcp-harness/
  build_goals.yaml          # 藍圖（已有）
  task_list.yaml            # 執行期 SSOT（待實作，執行時產生）
  task_list.example.yaml    # 範本（待新增）
  core/
    pipeline/
      schema.py             # task_list 資料類型
      store.py              # 讀寫 YAML、原子更新
      plan_normalize.py     # build_goals → normalized_tasks（LLM，§2.1）
      bootstrap.py          # normalized_tasks → task_list
      runner.py             # 執行期 Phase 1–4 與 LangGraph 整合
      context.py            # Token 友善的 actual_* 摘要
  tasks.py                  # 保留：載入 build_goals、組 prompt
  build_workflow.py         # 改為呼叫 core.pipeline.runner
  unity_common.py           # 保留：MCP 註冊與 Chat
  run_build.py
  docs/
    HARNESS.md              # 本文件
    TO_HARNESS.md           # 遷移步驟
```

**外部依賴（不在本 repo 內實作）**：

- **MCP Server**：Coplay Unity MCP（Editor + relay）。
- **可選未來**：自訂 Unity Editor 擴充（`Undo.RecordObject`、精簡 Read API）— 對應原白皮書 `/unity-extension`。

---

## 8. 與現有 `build_workflow` 的整合方式（目標）

```
build_goals.yaml
       │
       ▼
core.pipeline.plan_normalize  (LLM，可選寫回 build_goals)
       │
       ▼
core.pipeline.bootstrap ──> task_list.yaml
       │
build_workflow (LangGraph)   │
       │                     │
       └──> core.pipeline.runner
                 │   執行期 Phase 1–4 更新 task_list
                 └──> UnityMCPRunner.ask(prompt + harness context)
```

- **plan_normalize**：補齊任務契約（§2.2）；可擴充任務數；預設不呼叫 Unity MCP。
- **LangGraph** 仍負責「依序取下一個未完成任務」。
- **Harness pipeline** 負責每步前後的結構化狀態與落盤，而非僅追加文字 `prior_results`。

---

## 9. 建議加分項（中長期）

1. **Delta-only Context**：讀取工具帶 `filters`，只傳 `Renderer` / `Transform` 等必要欄位，控制 token。
2. **Undo / Rollback**：Phase 3 驗證失敗時呼叫 `Execute_Undo`（需 Unity 側工具），並標記 `failed`。
3. **HTTP MCP**：長連線 Editor server，減少 relay 子行程與重複核准（見 `docs/NOTE.md`）。
4. **CLI 更名**：`unity-mcp-harness` 或 `harness-build`，與套件名 `pyproject.toml` 對齊。

---

## 10. 相關文件

- [TO_HARNESS.md](./TO_HARNESS.md) — 由現況到 Harness 的實作步驟
- [README.md](../README.md) / [docs/README.md](./README.md) — 安裝與 CLI
- [BUILD.md](./BUILD.md) — LangGraph 建構流
- [NOTE.md](./NOTE.md) — 踩坑（核准、模型、stdio/HTTP）
