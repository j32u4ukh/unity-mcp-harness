# `unity-mcp-harness` 框架的架構設計白皮書（Framework Specification）

它兼具兩個核心任務：

1. **對內（給 Cursor）：** 讓 Cursor 理解整個專案的靈魂架構（閉環控制、動態任務注入、狀態持久化），以便它能準確地為你重構專案結構、擴充底層的 Python 膠水層或 Unity C# Side。
2. **對外（給執行中的 Agent）：** 當你的自主 Agent（LLM）啟動並載入這個專案時，它會讀取這份文件作為它的**行動指南（Runtime Guide）**，明白自己在調用 MCP Tool 時必須遵循「感知 $\rightarrow$ 行動 $\rightarrow$ 驗證」的範式，不能瞎子摸象。

以下為你重新精煉、優化後的完整主文件 Markdown。你可以將其命名為 `FRAMEWORK_SPECIFICATION.md` 或 `README.md` 直接放入專案根目錄。

---

```markdown
# Unity MCP Harness Framework Specification

`unity-mcp-harness` 是一個基於 Anthropic Model Context Protocol (MCP) 的主動式、具備閉環控制（Closed-Loop Control）的 Unity 自動化操作框架。

本文件定義了框架的核心架構、代理人（Agent）的行為範式、以及任務持久化規範。本專案的所有模組重構與 Agent 執行邏輯，皆須嚴格遵循此規範。

---

## 1. 核心設計哲學 (Core Philosophy)

傳統的自動化腳本或盲目型 Agent 往往採用「發射後不管（Fire and Forget）」的模式，這在複雜的 Unity 編輯器環境中會導致嚴重的幻覺與操作衝突。`unity-mcp-harness` 核心哲學為 **「無感知，不行動」**：

1. **狀態冪等性 (State Idempotency):** 任何變更操作前，必須先驗證當前現場狀態。若目標狀態已達成，則視為任務完成，不重複執行。
2. **動態依賴解析 (Dynamic Dependency Resolution):** Agent 遭遇組件或資源缺失時，不直接報錯中斷，而是將其抽象化為「前置子任務」動態注入執行隊列。
3. **驗證與斷言 (Assertion Verification):** 操作完成後必須立即進行二次感知，比對「實際狀態」與「預期狀態」，確保操作真實生效。
4. **狀態持久化與斷點續傳 (State Persistence):** 所有的任務階段、感知數據與驗證結果皆即時落盤為 YAML 檔案，支援隨時中斷、隨時接續。

---

## 2. 狀態感知型操作流水線 (The Pipeline)

不論是 Agent 的決策核心，還是底層的 MCP Tool 封裝，都必須圍繞以下四階段的「閉環控制流水線」進行建構：


```

+------------------+     成功 (狀態已滿足)     +------------------+
|  Phase 1: 感知    |------------------------>|  Phase 4: 持久化  |
|  (Pre-Perception)|                         |  (Persistence)   |
+------------------+                         +------------------+
| 狀態未滿足                                 ^
v                                           |
+------------------+   缺少必要組件 (觸發注入)        |
|  Phase 2: 決策   |-----------------+               |
|  (Decision/Act)  |                 |               |
+------------------+                 v               |
| 條件具備        +-------------------+     |
v                 | 動態新增前置任務   |     |
+------------------+       | (Task Injection)  |     |
|  Phase 3: 驗證    |       +-------------------+     |
| (Post-Assertion) |                 |               |
+------------------+                 +---------------+
|                           (更新依賴樹並返回)
+-------------------------------------------+
驗證通過 / 失敗歸檔

```

### Phase 1: 操作前感知 (Pre-Perception)
* **Agent 行為：** 在對任何 Unity 物件（GameObject/Asset）進行修改前，必須先調用讀取類型的 MCP Tool（例如 `get_inspector_state`）獲取當前真實狀態（如：顏色、坐標、組件列表）。
* **上下文注入：** 框架或 Agent 必須將此即時狀態作為上下文（Context）注入到當前的 Prompt 思考鏈中。

### Phase 2: 決策與動態規劃 (Decision & Dynamic Planning)
* **分支 A (冪等跳過)：** 若當前狀態已符合預期（例：物件已經是紅色），Agent 應直接判定此步驟完成，跳至 Phase 4。
* **分支 B (常規執行)：** 若狀態未滿足且條件具備，調用修改類型的 MCP Tool（例如 `set_component_property`）。
* **分支 C (動態任務注入)：** 若發現缺乏操作先決條件（例：欲修改顏色但物件上根本沒有 `MeshRenderer` 組件），Agent 必須暫停主任務，在執行隊列（`task_list.yaml`）中**動態新增**一項優先權更高、用於補齊組件的前置子任務。

### Phase 3: 操作後驗證 (Post-Assertion)
* **Agent 行為：** 修改指令執行完畢後，**禁止**直接假設其已成功。Agent 必須再次調用讀取類型的 MCP Tool 重新掃描現場。
* **斷言比對：** 比較「操作後的實際狀態」與「預期目標狀態」。
  * **一致：** 驗證通過，推進任務。
  * **不一致：** 觸發錯誤分析（分析是否受 Prefab 保護、唯讀限制或腳本衝突），嘗試修正或標記失敗。

### Phase 4: 進度持久化 (Persistence)
* **框架行為：** 將本次感知的 `actual_before`、`actual_after` 以及任務最終狀態即時更新至 `task_list.yaml`。
* **斷點續傳：** 當 `unity-mcp-harness` 重啟時，會自動解析該 YAML 檔案，跳過 `status: completed` 的項目，定位到第一個未完成的任務，並**重新進行 Phase 1 感知**以校準現場。

---

## 3. 執行隊列持久化規範 (Task List Schema)

專案根目錄下的 `task_list.yaml` 是 Agent 與外部框架通訊的唯一單一事實來源（Single Source of Truth）。其結構規範如下：

```yaml
project_name: "unity-mcp-harness-runtime"
last_updated: "2026-05-25T22:00:00Z"
current_lifecycle_phase: "Scene_Verification"

tasks:
  - id: "task_001"
    description: "Ensure 'Enemy_Spawn_Point' has a red visual indicator"
    status: "completed" # 可選值: pending | in_progress | completed | failed
    target:
      game_object: "Enemy_Spawn_Point"
      path: "/Stage1/Managers/Enemy_Spawn_Point"
    pipeline_records:
      actual_before:
        components: ["Transform", "MeshRenderer"]
        properties:
          "MeshRenderer.sharedMaterial.color": "RGBA(1.000, 1.000, 1.000, 1.000)"
      operations_executed:
        - timestamp: "2026-05-25T21:58:00Z"
          action: "Modify_Property"
          field: "MeshRenderer.sharedMaterial.color"
          value: "RGBA(1.000, 0.000, 0.000, 1.000)"
      actual_after:
        properties:
          "MeshRenderer.sharedMaterial.color": "RGBA(1.000, 0.000, 0.000, 1.000)"
    verification: "verified_verified_by_mcp_reader"

  - id: "task_002"
    description: "Set 'Boss_Core' color to red"
    status: "in_progress"
    target:
      game_object: "Boss_Core"
      path: "/Stage1/Entities/Boss_Core"
    pipeline_records:
      actual_before:
        components: ["Transform"] # 👈 Phase 1 發現缺少 MeshRenderer！
      operations_executed:
        - timestamp: "2026-05-25T22:00:00Z"
          action: "Dynamic_Task_Injection" # 👈 Agent 自動動態注入前置步驟
          injected_subtask: "Add_Component_MeshRenderer"
          status: "completed"
        - timestamp: "2026-05-25T22:00:15Z"
          action: "Modify_Property"
          field: "MeshRenderer.sharedMaterial.color"
          value: "RGBA(1.000, 0.000, 0.000, 1.000)"
      actual_after:
        properties:
          "MeshRenderer.sharedMaterial.color": "pending"
    verification: "pending"

```

---

## 4. 給 Agent 的行動與思考指導 (Guidance for Runtime Agent)

當 Agent 載入此專案並開始操作 Unity MCP 時，必須內化以下思考模型（CoT）：

1. **接到指令時：**
* *❌ 錯誤思考：* 「使用者要我把物件改為紅色，我現在立刻調用 `set_color` 工具。」
*  正確思考：* 「使用者要我把物件改為紅色。我必須先調用 `get_state` 工具，看看這個物件目前存在嗎？它有 `MeshRenderer` 嗎？它原本是什麼顏色？」


2. **發現缺少組件時：**
* *❌ 錯誤思考：* 「糟糕，物件沒有 `MeshRenderer`，我無法改顏色，直接回報錯誤給使用者。」
*  正確思考：* 「物件缺少 `MeshRenderer`。根據 Harness 規範，我應該先調用 `add_component` 工具（並在 `task_list.yaml` 紀錄動態注入步驟），完成後再重新執行改顏色的任務。」


3. **執行修改後：**
* *❌ 錯誤思考：* 「我已經發送了修改顏色的 API，現在跟使用者說我做完了。」
*  正確思考：* 「修改指令已發送。我現在必須再次調用 `get_state`，確認 Unity 編輯器回傳的真實顏色確實是紅色。確認無誤後，將 YAML 狀態改為 `completed`。」



---

## 5. 專案架構調整方向 (Project Restructuring Target)

為了支援上述流水線，Cursor 與開發者在調整專案結構時，應確保以下模組的職責劃分：

* **`/core/pipeline` (Python/Go 核心層):** 負責解析 `task_list.yaml`，控管任務生命週期，並將 Phase 1 讀取到的現場狀態格式化為 Token 友善的 Context 餵給 Agent。
* **`/mcp-server/tools` (MCP 接口層):** 所有的修改類 Tool（Write Operations）應儘可能內聚安全檢查；所有的讀取類 Tool（Read Operations）必須提供精準、輕量化的 Property 層級過濾，避免全量讀取導致 Token 膨脹。
* **`/unity-extension` (Unity C# 側):** 負責與 Unity 編輯器底層交互（透過 `UnityEditor` 命名空間）。必須支援 `Undo.RecordObject` 整合，當 Phase 3 驗證連續失敗時，配合框架提供自動回滾（Rollback）機制，確保編輯器現場不被髒數據污染。

```

***

### 💡 對於專案微調與 Agent 讀取時的加分點（建議）：

1. **Token 優化機制（Delta-only Context）：** 在這個架構下，Agent 操作大型 Unity 場景時很容易因為讀取太多 Component 資訊而導致 Context 爆炸。你可以讓 Cursor 在優化 `/mcp-server/tools` 時，加上 `filters` 參數（例如只讀取 `Renderer` 相關屬性），讓 Agent 在 Phase 1 感知時只拿需要的資料。
2. **新增 `Undo` 機制：** 文件第 5 點我幫你加上了 Unity 的 `Undo` 整合。當 Agent 發現「改完之後驗證失敗」（例如可能被其他 Runtime 腳本覆蓋、或者材質是唯讀的變更無效），它可以呼叫一個 `Execute_Undo` 的 Tool，把場景恢復，然後在 YAML 標記 `failed` 退出，這會讓你的整個 harness 架構非常安全且強健。

```