# `unity-mcp` → `unity-mcp-harness` 遷移計畫

本文件依 [HARNESS.md](./HARNESS.md) 規格，列出**由現況（Agent + Unity MCP）到可運作 Harness（閉環 + 持久化）**的建議實作順序。  
每步完成後應可獨立驗證；不必一次做完 §5–§9 才開始使用 CLI。

**現況摘要**：已有 `build_goals.yaml`、`tasks.py`、`build_workflow.py`、`unity_common.py`、`harness/mcp_runner`、`core/pipeline`（schema/store/plan_normalize/bootstrap）、Coplay MCP；**已具備** Plan Normalize + bootstrap 至 `task_list.yaml`（`run_build` 啟動鏈）；**已具備** 執行期 prompt 以 `task_list` 為準 + Harness 上下文注入（階段 3）；**尚無** 框架級每步落盤（階段 4+）。  
**設計要點**：人類撰寫的 `build_goals.yaml` 不必逐條符合 HARNESS 執行契約；無 `task_list.yaml` 或 `--replan` 時會 LLM 規範化（可 3→N）再 bootstrap（見 HARNESS §2.1、階段 1.5）。

**跨套件債務（0.5 已完成）**：`UnityMCPRunner` 已遷入 **unity-mcp-harness**；aicentral-agent 僅保留通用 LangGraph。

---

## 執行清單（逐條勾選）

建議依序執行；**0.5 與階段 1 可並行**。完成後在 `[ ]` 改為 `[x]`。細節與驗證方式見下方各階段章節。

### 階段 0 — 命名與文件

- [x] **0.1** `pyproject.toml`：`name` → `unity-mcp-harness`；entry points 可保留 `unity-mcp-build`
- [x] **0.2** `README.md`：Harness 定位 + 連結 `HARNESS.md`、`TO_HARNESS.md`
- [x] **0.3** `docs/NOTE.md` 架構圖：`workflow.py` → `build_workflow.py`

### 階段 0.5 — UnityMCPRunner 歸位（harness ← aicentral-agent）

- [x] **0.5** 遷入 `mcp_build.py` → `harness/mcp_runner.py`（或 `unity_common`）；遷入 `tests/test_mcp_runner.py`；更新 `pyproject` 套件佈局
- [x] **0.5.2a** `build_workflow.py` 改 import 本 repo，移除 `aicentral_agent.mcp_build`
- [x] **0.5.2b** `unity_common.create_unity_chat` 單一註冊路徑
- [x] **0.5.2c** `pyproject.toml` 視情況移除 `aicentral-agent` 依賴
- [x] **0.5.2d** `scripts/build_exe.ps1` 移除 `--collect-submodules aicentral_agent`
- [x] **0.5.3a** aicentral-agent：刪除或 deprecated `mcp_build.py`
- [x] **0.5.3b** aicentral-agent `__init__.py` 移除 Unity 相關匯出
- [x] **0.5.3c** aicentral-agent：刪除 `tests/test_mcp_build.py`
- [x] **0.5.3d** aicentral-agent README：改指向 unity-mcp-harness
- [ ] **0.5.3e**（可選）deprecated re-export + `DeprecationWarning`
- [x] **0.5.4a** `HARNESS.md` §0.1 MCP 層描述更新
- [x] **0.5.4b** `NOTE.md` 架構圖更新
- [x] **0.5✓** monorepo 搜尋 `aicentral_agent.mcp_build` / `UnityMCPRunner` 匯入為零（或僅 deprecated）

### 階段 1 — 執行期 SSOT 資料模型

- [x] **1.1** `core/pipeline/schema.py`：`HarnessTask`、`PipelineRecords`、`TaskListDocument`
- [x] **1.2** `task_list.example.yaml`
- [x] **1.3** `core/pipeline/store.py`：`load_task_list` / `save_task_list`（原子寫入）
- [x] **1.4** `.gitignore` 加入 `task_list.yaml`
- [x] **1.5** `schema`：`NormalizedPlan`、`plan_revision`、`plan_source_id`、`plan_changelog`

### 階段 1.5 — 藍圖規範化（Plan Normalize）

- [x] **1.5.1** `core/pipeline/plan_normalize.py`：`normalize_plan()`
- [x] **1.5.2** 結構化輸出：`normalized_tasks[]` + `plan_changelog`
- [x] **1.5.3** 支援 3 條粗任務 → N 條子任務
- [x] **1.5.4** 啟動鏈：`prepare_harness_queue` → normalize → bootstrap；`--skip-plan-normalize`
- [x] **1.5.5** CLI `--replan` / `--init-tasks`
- [x] **1.5.6**（可選）`--write-back-goals` / `--backup`
- [x] **1.5.7**（可選）`--plan-with-mcp`
- [x] **1.5.8** `tests/test_plan_normalize.py`、`tests/test_bootstrap.py`

### 階段 2 — Bootstrap 執行隊列

- [x] **2.1** `bootstrap.py`：輸入 `NormalizedPlan` → `task_list.yaml`（含 replan 保留 completed）
- [x] **2.2** CLI：`--init-tasks` / `--replan`；`--dry-run` 顯示 plan_revision 與 task_list

### 階段 3 — 執行期 Prompt（軟 Harness）

- [x] **3.1** `core/pipeline/context.py`：SSOT 摘要格式化
- [x] **3.2** 擴充 `format_task_prompt` + HARNESS CoT
- [x] **3.3** 執行 prompt 以 `task_list` 為準（非原始藍圖 `tasks[].prompt`）
- [x] **3.4** 憲法留 `system_context`；逐步 CoT 由 Normalize 寫入各任務

### 階段 4 — LangGraph + 每步落盤

- [ ] **4.1** `core/pipeline/runner.py`：`on_task_start` / `on_task_end` + 本 repo `UnityMCPRunner`
- [ ] **4.2** `build_workflow._run_single_task` 掛 hook + `save_task_list`
- [ ] **4.3** `run_build.py` 依 `task_list` 取下一個非 `completed` 任務

### 階段 5 — 斷點續傳

- [ ] **5.1** `get_next_runnable_task()`；`--retry-failed`（可選）
- [ ] **5.2** 重啟後 prompt 強制重新 Phase 1 感知

### 階段 6 — 結構化感知/驗證（硬 Harness）

- [ ] **6.1** `core/pipeline/tool_adapter.py`：Read/Write 慣例 + `operations_executed`
- [ ] **6.2** 任務欄位 `harness.pre_read` / `harness.post_read`
- [ ] **6.3** 失敗 → `status: failed`、`verification: failed`
- [ ] **6.4** 冪等跳過 → `verification: skipped_by_idempotent`

### 階段 7 — 執行期動態任務注入

- [ ] **7.1** `store.inject_subtask()`
- [ ] **7.2** `[HARNESS_INJECT:...]` 或 tool 觸發
- [ ] **7.3** `get_next_runnable_task` 尊重 `priority` / 插入序

### 階段 8 — 藍圖同步

- [ ] **8.1** CLI `sync-plan` / `--sync-plan`（normalize + 合併至 task_list）
- [ ] **8.2** `--write-back-goals`：僅寫回規劃期欄位，不寫 `actual_*` / `verification`
- [ ] **8.3** 維護指南：何時 `--replan` / 改 task_list / 寫回藍圖

### 階段 9 — 測試與可觀測性

- [ ] **9.1** `test_pipeline_store.py`、`test_bootstrap.py`
- [ ] **9.2** `--dry-run`：normalize + bootstrap 或讀既有 task_list
- [ ] **9.3**（可選）`--json` 含 `verification`
- [ ] **9.4** `test_plan_normalize_writeback.py`

### 階段 10 — 中長期（可並行規劃，非 v1 必須）

- [ ] **10.1** Unity Editor：精簡 inspector / filters
- [ ] **10.2** `Execute_Undo` / Phase 3 回滾
- [ ] **10.3** HTTP MCP 長連線
- [ ] **10.4** 持久 MCP session（aicentral）
- [ ] **10.5** CLI 更名 `unity-mcp-harness`

### Harness v1 完成定義（全部滿足即 v1）

- [ ] **DoD-1** 啟動時 Plan Normalize → bootstrap `task_list.yaml`
- [ ] **DoD-2** 每步結束更新 `status`、`operations_executed`
- [ ] **DoD-3** 重跑跳過 `completed`，續跑 `pending`
- [ ] **DoD-4** 粗藍圖 + `--replan` / `sync-plan` / 可選寫回，無需重編 exe
- [ ] **DoD-5** `HARNESS.md` 與 `core/pipeline` 模組一致
- [ ] **DoD-6** 2D 範例整合路徑跑通，`validate_2d_scene` 落盤 `verification`
- [ ] **DoD-7** 不依賴 aicentral-agent Unity 模組

---

## 階段 0：對齊命名與文件（低風險）

| # | 工作項 | 產出 | 驗證 |
|---|--------|------|------|
| 0.1 | `pyproject.toml`：`name` 改為 `unity-mcp-harness`；entry points 可保留 `unity-mcp-build` 或新增別名 | 套件名與 repo 一致 | `pip install -e .` 成功 |
| 0.2 | `README.md` 開頭改為 Harness 定位，連結 `docs/HARNESS.md`、`docs/TO_HARNESS.md` | 新人知道藍圖 vs 執行期檔 | 人工閱讀 |
| 0.3 | `docs/NOTE.md` 架構圖：`workflow.py` → `build_workflow.py` | 與程式一致 | — |

**不依賴程式大改，可先合併。**

---

## 階段 0.5：Unity MCP Runner 歸位（自 aicentral-agent 遷入）

將 **Unity 專用** MCP 橋接從 `aicentral-agent` 移入 `unity-mcp-harness`，讓 aicentral-agent 只保留通用 Agent（`ChatAicentral`、`build_chat_graph`、`build_react_agent` 等）。本階段可與階段 1 並行，但建議在階段 4 擴充 `core/pipeline/runner.py` **之前**完成，避免 runner 依賴外套件。

### 0.5.1 自 `aicentral-agent` 遷入的程式（清單）

| 來源（aicentral-agent） | 目標（unity-mcp-harness） | 說明 |
|-------------------------|---------------------------|------|
| `src/aicentral_agent/mcp_build.py` | `harness/mcp_runner.py`（或併入 `unity_common.py`） | `UnityMCPRunner`、`create_unity_mcp_runner`、`ask_unity_mcp`、`register_unity_mcp_servers` |
| `tests/test_mcp_build.py` | `tests/test_mcp_runner.py` | mock `Chat.with_mcp`，無需 Unity |
| — | 更新 `pyproject.toml` `[tool.setuptools.packages]` 或改為 package 佈局 | 若新增 `harness/` 套件目錄 |

**遷入後實作要點**（邏輯不變，僅改歸屬與 import）：

- `UnityMCPRunner`：封裝 `Chat.with_mcp` 的 `ask()`，供多任務共用同一 `Chat` 工作階段。
- `create_unity_mcp_runner`：呼叫 `register_unity_servers`（**應委派** `unity_common.register_unity_servers`，勿重複 `register_unity_mcp_servers` 與 `unity_servers.json` 兩套註冊邏輯）。
- `ask_unity_mcp`：單次問答；與 `unity_common.ask_unity` 評估**合併**，避免雙入口。

### 0.5.2 修改 `unity-mcp-harness` 內引用

| # | 工作項 | 產出 | 驗證 |
|---|--------|------|------|
| 0.5.2a | `build_workflow.py`：`from harness.mcp_runner import …`（或 `from unity_common import create_unity_mcp_runner`） | 不再 import `aicentral_agent` | `pytest tests/test_workflow.py` |
| 0.5.2b | `unity_common.py`：`create_unity_chat` 改呼叫本 repo 的 `create_unity_mcp_runner`，刪除對 `aicentral_agent.mcp_build` 的 lazy import | 單一註冊路徑 | `unity-mcp-ask` 煙霧測試（可選） |
| 0.5.2c | `pyproject.toml`：視情況**移除** `aicentral-agent` 依賴（若全 repo 無其他 `aicentral_agent` import） | 依賴圖清晰 | `pip install -e .`；僅保留 `aicentral[mcp]`、`langgraph` |
| 0.5.2d | `scripts/build_exe.ps1`：移除 `--collect-submodules aicentral_agent`（若已不再依賴） | 縮小 exe 體積 | 打包後 `unity-mcp-build.exe --dry-run` |

### 0.5.3 清理 `aicentral-agent`（僅文件與匯出，程式刪除或棄用）

| # | 工作項 | 產出 | 驗證 |
|---|--------|------|------|
| 0.5.3a | 刪除或標記 deprecated：`mcp_build.py` | 無 Unity 程式碼留在 agent 套件 | `aicentral-agent` 內無 `unity` 模組 import |
| 0.5.3b | `__init__.py`：移除 `UnityMCPRunner`、`create_unity_mcp_runner`、`ask_unity_mcp`、`register_unity_mcp_servers` 的匯出 | 對外 API 僅通用 Agent | `from aicentral_agent import ChatAicentral` 仍可用 |
| 0.5.3c | 刪除 `tests/test_mcp_build.py`（已遷至 harness） | 測試歸位 | `aicentral-agent` 的 `pytest` 通過 |
| 0.5.3d | `README.md`、`docs/README.md`：「與 unity-mcp 搭配」改為「Unity 建構請用 **unity-mcp-harness**」；刪除「本專案提供 `UnityMCPRunner`」類敘述 | 文件邊界一致 | 人工閱讀 |
| 0.5.3e | 可選：在 `mcp_build.py` 位置留 `DEPRECATED.md` 或 re-export 一版（發出 `DeprecationWarning` 指向 harness） | 過渡期相容 | 舊腳本若仍 import 會看到警告 |

### 0.5.4 更新本 repo 文件

| # | 工作項 | 產出 |
|---|--------|------|
| 0.5.4a | [HARNESS.md](./HARNESS.md) §0.1：MCP 層改為「harness 內 `mcp_runner` + `unity_common`」 |
| 0.5.4b | [NOTE.md](./NOTE.md) 架構圖：`aicentral-agent UnityMCPRunner` → `harness` / `unity_common` |

### 0.5.5 不屬於遷移、保留在 aicentral-agent 的內容

以下為**通用 Agent**，留在 aicentral-agent，**不要**移入 harness：

- `llm.py` — `ChatAicentral`
- `graph.py` — `build_chat_graph`、`build_react_agent`、`invoke_graph`
- `messages.py` — LangChain ↔ aicentral 訊息轉換
- `examples/simple_graph.py`、`examples/react_agent.py`
- `common.py` — `require_aicentral_config`（harness 已有自有的 `unity_common.require_aicentral_config` / `bootstrap_aicentral_config`）

以下留在 **aicentral**（底層能力），harness 繼續依賴：

- `Chat.with_mcp`、`MCPManager`、`register_mcp_servers`（執行期註冊）

**驗證（階段 0.5 完成）**：全 monorepo 搜尋 `aicentral_agent.mcp_build` / `from aicentral_agent import UnityMCPRunner` 應只剩 aicentral-agent 內可選的 deprecated re-export（或為零）。

---

## 階段 1：執行期 SSOT 資料模型

| # | 工作項 | 產出 | 驗證 |
|---|--------|------|------|
| 1.1 | 新增 `core/pipeline/schema.py`（或 `harness/schema.py`）：`HarnessTask`、`PipelineRecords`、`TaskListDocument` dataclass | 型別定義 | import 無誤 |
| 1.2 | 新增 `task_list.example.yaml`（對齊 HARNESS §4，id 與 `build_goals.yaml` 六任務一致） | 範本可提交版控 | YAML 可被 1.3 載入 |
| 1.3 | 新增 `core/pipeline/store.py`：`load_task_list` / `save_task_list`（原子寫入 `.tmp` + replace） | 讀寫 API | 單元測試 roundtrip |
| 1.4 | `.gitignore` 加入 `task_list.yaml`（保留 `task_list.example.yaml`） | 執行檔不污染版控 | — |
| 1.5 | `schema` 增加 `NormalizedPlan`、`plan_revision`、`plan_source_id`、`plan_changelog` | 支援規劃期輸出 | 單元測試載入範例 JSON |

---

## 階段 1.5：藍圖規範化（Plan Normalize）

在 bootstrap 與任何 Unity MCP 執行**之前**，用 LLM 將 `build_goals.yaml` 的粗任務轉為符合 HARNESS §2.2 的執行任務列表。本階段解決「規範寫在文件裡，但藍圖 prompt 無法強制遵守」的問題。

| # | 工作項 | 產出 | 驗證 |
|---|--------|------|------|
| 1.5.1 | 新增 `core/pipeline/plan_normalize.py`：`normalize_plan(build_goals) -> NormalizedPlan`；固定 system prompt（HARNESS 任務契約 + 2D 憲法摘要） | 規劃 API | mock LLM 回傳結構化 YAML |
| 1.5.2 | 結構化輸出：要求 LLM 回傳 `normalized_tasks[]` + `plan_changelog`（禁止自由散文）；可用 JSON schema / `response_format` | 可解析 | 故意缺 `pre_read` 的輸入 → 輸出補齊 |
| 1.5.3 | 支援**任務數變化**：輸入 3 條粗任務 → 輸出 ≥3 條可執行子任務（對齊現有 2D 六任務或更多） | 動態擴充 | 單元測試：3 in / 6 out |
| 1.5.4 | `run_build` / `build_workflow` 啟動鏈：`load_build_goals` → `normalize_plan` → `bootstrap`；`--skip-plan-normalize` 僅除錯用 | 預設路徑含規範化 | 無旗標時日誌有 `plan_revision` |
| 1.5.5 | CLI `--replan`：強制重跑 Normalize + 重建 `task_list`（不覆寫 `completed` 的 `pipeline_records`，或提示備份） | 藍圖大改可重規劃 | 改 `build_goals` 後 `--replan` 任務數更新 |
| 1.5.6 | 可選 `--write-back-goals`：將 `normalized_tasks` 合併寫回 `build_goals.yaml`（`--backup` 產生 `.bak`） | 藍圖與執行隊列對齊 | diff 顯示新增子任務與改寫 prompt |
| 1.5.7 | 可選 `--plan-with-mcp`：規劃階段唯讀 MCP（如 `Unity_ListResources`）輔助拆任務；預設關閉 | 複雜專案 | 僅 list 無 write |
| 1.5.8 | `tests/test_plan_normalize.py`：mock Chat，無 Unity | 無 Editor 單測 | `pytest` 通過 |

**與階段 7 的邊界**：1.5 在**啟動前**擴充/改寫任務定義；階段 7 在**執行中**依 MCP 現場插入子任務。兩者皆寫 `task_list`，僅 1.5 可寫回 `build_goals`。

---

## 階段 2：由規範化結果 bootstrap 執行隊列

| # | 工作項 | 產出 | 驗證 |
|---|--------|------|------|
| 2.1 | 修改 `core/pipeline/bootstrap.py`：輸入為 **`NormalizedPlan`**（非直接 parse 原始 `tasks`），寫入 `task_list.yaml`（`status: pending`、`plan_revision`、`plan_source_id`） | 首次執行前自動產生 | 藍圖 3 條經 1.5 後 bootstrap 得到 N 筆 pending |
| 2.2 | CLI：`--init-tasks` 或 `run_build` 開頭：`normalize` → `bootstrap`（若無 `task_list` 或 `--replan`） | 使用者不需手動複製 | `unity-mcp-build --dry-run` 列出 N 任務與 `plan_revision` |

**階段 2 依賴 1.5**；dry-run 可只跑 normalize+bootstrap、不跑 Unity MCP。

---

## 階段 3：Prompt 注入執行期狀態（軟 Harness）

| # | 工作項 | 產出 | 驗證 |
|---|--------|------|------|
| 3.1 | 新增 `core/pipeline/context.py`：將當前任務的 `pipeline_records`、`status` 格式化成短摘要 | Token 友善 | 單元測試固定輸入輸出 |
| 3.2 | 擴充 `tasks.format_task_prompt`（或 pipeline 包一層）：併入 Harness 上下文 + HARNESS §6 CoT 要點 | Agent 每步看到 SSOT | prompt 含 `actual_before` 占位 |
| 3.3 | 執行期 prompt 以 **`task_list` 內已規範化的 `prompt`** 為準（非直接讀原始藍圖 `tasks[].prompt`） | 與 1.5 銜接 | 藍圖粗 prompt 與執行 prompt 可不同 |
| 3.4 | `build_goals` 的 `system_context` 可保留高層憲法；**逐步 CoT 句式**由 Plan Normalize 寫入各任務 `prompt` | 分工清楚 | 人工檢查 normalize 輸出 |

**執行期仍由 LLM 決定 MCP 呼叫；但任務定義應已在 1.5 合規。上下文接軌 `task_list.yaml`。**

---

## 階段 4：與 LangGraph 整合（每步落盤）

| # | 工作項 | 產出 | 驗證 |
|---|--------|------|------|
| 4.1 | 新增 `core/pipeline/runner.py`：`on_task_start` / `on_task_end`；內部使用 **本 repo** 的 `UnityMCPRunner`（階段 0.5 後禁止依賴 `aicentral_agent`） | 生命週期 hook | mock runner 測試 |
| 4.2 | 修改 `build_workflow._run_single_task`：前後呼叫 pipeline hook；每步結束 `save_task_list` | Phase 4 最低限度 | 跑 1 任務後 `task_list.yaml` 有 `in_progress` / `completed` |
| 4.3 | `run_build.py` 啟動時 `load_task_list`，迴圈取**下一個非 completed** 任務（而非僅 `task_index`） | 與 SSOT 對齊 | 手動改 yaml 為 `completed` 後重跑會跳過 |

---

## 階段 5：斷點續傳（Resume）

| # | 工作項 | 產出 | 驗證 |
|---|--------|------|------|
| 5.1 | `enabled_tasks()` 或 pipeline：`get_next_runnable_task()` 跳過 `completed` / `failed`（`failed` 可選 `--retry-failed`） | 重啟接續 | 完成前 3 步後中斷，再跑只執行後 3 步 |
| 5.2 | 對下一任務強制在 prompt 註明：**重啟後須重新 Phase 1 感知**（即使上一輪文字摘要存在） | 校準現場 | 文件中標註即可，實作靠 prompt |

---

## 階段 6：結構化感知/驗證（硬 Harness，第一版）

| # | 工作項 | 產出 | 驗證 |
|---|--------|------|------|
| 6.1 | 新增 `core/pipeline/tool_adapter.py`：約定「讀取」= 先呼叫 `Unity_ListResources` / 唯讀 `Unity_RunCommand`；紀錄 `tool` 名至 `operations_executed` | 可選由框架先打一遍讀取 | 日誌中有 `MCP_Read` 紀錄 |
| 6.2 | 任務 YAML 可選欄位 `harness.pre_read` / `harness.post_read`（工具提示或 C# 片段） | 每任務可配置 | `create_2d_scene` 讀場景路徑 |
| 6.3 | `on_task_end`：若 `task_reply_indicates_failure` → `status: failed`，`verification: failed` | 與現有啟發式整合 | 故意 revoked 時 yaml 為 failed |
| 6.4 | 成功且回覆含「已存在，跳過」→ `verification: skipped_by_idempotent` | 冪等可追蹤 | 重跑第二遍狀態正確 |

**不必等新 MCP Server；先用 Coplay 工具 + 紀錄結構落地。**

---

## 階段 7：動態任務注入

| # | 工作項 | 產出 | 驗證 |
|---|--------|------|------|
| 7.1 | `store.inject_subtask(parent_id, subtask_spec, priority)`：插入隊列並設 `injected_by` | API | 單元測試插入順序 |
| 7.2 | Prompt 規定：缺組件時輸出固定標記 `[HARNESS_INJECT:...]`，或由 tool 結果觸發 | 觸發方式二選一 | 模擬缺 SpriteRenderer 插入 `add_sprite_renderer` 任務 |
| 7.3 | `get_next_runnable_task` 尊重 `priority` / 插入序 | 先執行子任務 | 整合測試 |

---

## 階段 8：與 `build_goals` 同步策略

| # | 工作項 | 產出 | 驗證 |
|---|--------|------|------|
| 8.1 | CLI：`sync-plan` / `--sync-plan`：人類改藍圖後，可選 **先 `normalize_plan` 再合併** 至 `task_list`，不覆寫 completed 的 `pipeline_records` | 藍圖↔隊列雙向 | 藍圖新增粗任務 → sync 出現 pending 子任務 |
| 8.2 | 與 `--write-back-goals` 搭配：執行期穩定後將 `task_list` 中**規劃期產物**（id、prompt、harness 欄位）寫回藍圖；**不**寫回 `actual_*` / `verification` | 版控友好藍圖 | `build_goals` 任務數與上次 normalize 一致 |
| 8.3 | 文件：何時只改粗藍圖（觸發 `--replan`）、何時直接改 `task_list`、何時寫回藍圖 | 維護指南 | HARNESS §2.1–2.3 |

---

## 階段 9：測試與可觀測性

| # | 工作項 | 產出 | 驗證 |
|---|--------|------|------|
| 9.1 | `tests/test_pipeline_store.py`、`test_bootstrap.py` | 無 Unity 單測 | `pytest` 通過 |
| 9.2 | `unity-mcp-build --dry-run`：`normalize` + bootstrap 預覽（或讀既有 `task_list`） | 乾跑一致 | 列出 N 任務、`plan_revision`、status |
| 9.4 | `tests/test_plan_normalize_writeback.py`：`--write-back-goals` 不破壞 YAML 結構 | 寫回安全 | roundtrip parse |
| 9.3 | 可選：`--json` 輸出含每任務 `verification` | 利於 CI | — |

---

## 階段 10：中長期（可與主線並行規劃）

| # | 工作項 | 說明 |
|---|--------|------|
| 10.1 | Unity Editor 擴充：精簡 `get_inspector_state`、屬性 filters | 降低 Phase 1 token |
| 10.2 | `Execute_Undo` 與 Phase 3 失敗回滾 | HARNESS §9 |
| 10.3 | HTTP MCP + 長連線 | 減少 relay 核准問題 |
| 10.4 | 持久 MCP session（aicentral 層） | 見 `docs/daemon.md` 討論，與 Harness 正交 |
| 10.5 | 更名 CLI 為 `unity-mcp-harness` | 與套件一致 |

---

## 建議實作順序（依賴關係）

```
0 對齊命名/文件
 ↓
0.5 UnityMCPRunner 遷入 harness（與 1 可並行）
 ↓
1 schema + store + example
 ↓
1.5 Plan Normalize（藍圖 LLM 規範化；可選寫回 build_goals）
 ↓
2 bootstrap（吃 NormalizedPlan）
 ↓
3 context 注入 prompt          ← 執行期；任務 prompt 已由 1.5 規範化
 ↓
4 LangGraph + 每步落盤（依賴 0.5 的 runner 歸位）
 ↓
5 resume
 ↓
6 結構化讀寫紀錄
 ↓
7 動態注入
 ↓
8 sync-plan
 ↓
9 測試
並行規劃 → 10 中長期
```

---

## 完成定義（Definition of Done for「Harness v1」）

滿足以下條件可視為達到 **Harness v1**（相對現有 Agent+MCP）：

1. 啟動時對 `build_goals.yaml` 執行 **Plan Normalize**（預設一次 LLM）；粗任務可擴充為 N 條合規任務後 bootstrap 至 `task_list.yaml`。
2. 執行 `unity-mcp-build` 會更新 `task_list.yaml`，且每步結束有 `status` 與 `operations_executed` 摘要。
3. 中斷後重跑會跳過 `completed`，並繼續下一 `pending` 任務。
4. `build_goals.yaml` 可只寫意圖（甚至 3 條粗任務）；`--replan` / `sync-plan` / 可選 `--write-back-goals` 處理藍圖與隊列一致，無需重編 exe。
5. 文件 [HARNESS.md](./HARNESS.md) 與實際模組 `core/pipeline`（含 `plan_normalize.py`）一致。
6. 至少一條整合路徑：藍圖可為**少於**執行任務數的粗列表，經 Normalize 後在 **2D 範例**上跑通，且 `validate_2d_scene` 的 `verification` 落盤。
7. **不再**依賴 `aicentral-agent` 的 Unity 專用模組；`UnityMCPRunner` 與相關測試位於 `unity-mcp-harness`。

---

## 相關文件

- [HARNESS.md](./HARNESS.md) — 框架規格與現況對照
- [BUILD.md](./BUILD.md) — 現有 LangGraph 建構流
- [NOTE.md](./NOTE.md) — Unity 核准、stdio/HTTP、模型行為
