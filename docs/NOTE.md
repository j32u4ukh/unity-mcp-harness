# unity-mcp 使用備忘與踩坑紀錄

本文件整理實際串接 **Unity MCP Server**、**aicentral**、**unity-mcp-build** 時的注意事項，以及先前失敗的常見原因，供自建 Agent / CLI 流程參考。

---

## 架構速覽

```
build_goals.yaml  →  tasks.py（組 prompt）
       ↓
build_workflow.py / unity-mcp-build  →  aicentral-agent UnityMCPRunner
       ↓
aicentral Chat.with_mcp + MCP tool loop
       ↓
unity_servers.json 註冊的 transport（stdio relay / http）
       ↓
Unity Editor（MCP for Unity）
```

- **aicentral**：LLM 路由 + MCP orchestrator（`complete_with_mcp_loop`）。
- **aicentral-agent**：`create_unity_mcp_runner` / `UnityMCPRunner`（建構用 MCP 橋接；規劃遷入 harness，見 [TO_HARNESS.md](./TO_HARNESS.md) 階段 0.5）。
- **unity-mcp-harness**：任務 YAML、LangGraph 順序編排（`build_workflow.py`）、`unity_servers.json` 載入與 CLI。

---

## 為何先前「unity-mcp + aicentral」會失敗？

以下為實際除錯中出現過的問題，**多數與程式 bug 無關**，而是環境與模型行為。

### 1. Unity MCP 核准（Connection revoked）

**現象**：工具似乎被呼叫，但回傳 `Connection revoked`，或助理說「無法操作 Editor」。

**原因**：Unity **Project Settings → AI → Unity MCP** 未核准目前客戶端（stdio relay 或 Cursor），或連線被撤銷。

**處理**：

- Editor 保持開啟，MCP 外掛顯示已連線。
- 開啟自動核准，或對每次 tool 請求按 Approve。
- 再跑 `unity-mcp-list-tools --json` 確認能列工具。

### 2. 模型未使用 function calling（Ollama / 部分 Gemini）

**現象**：`unity-mcp-build` 第一步回覆長文「我無法…」，**沒有** `tool_calls`；或第二步才被 `task_reply_indicates_failure` 標成 FAIL。

**原因**：MCP tool loop 需 **OpenAI 形狀 `tool_calls`**。unity-mcp 預設 `model: gemini-flash`（`build_goals.yaml` / `unity_common.DEFAULT_LLM_MODEL`）；若模型只回文字、不調工具，orchestrator 會把文字當最終答案結束。Ollama `gemma4:e2b` 亦常如此。

**建議**：確認 `secret.yaml` 已填 `gemini.api_key`；若仍不調工具，於 `build_goals.yaml` 改 `model: cloud-chat`（OpenAI）。

**處理**：

- 在 `build_goals.yaml` 加：`model: cloud-chat`（或換支援 tools 的 Ollama 模型）。
- 單步驗證：`unity-mcp-ask "請呼叫 unity__Unity_ManageGameObject 建立 TestCube"`，看是否真的調工具。

### 3. 誤判成功（已改善）

**現象**：明明寫「未能成功建立」「工具調用失敗」，CLI 卻顯示 `[OK]`。

**原因**：舊版僅用少數關鍵字判斷失敗，未涵蓋「Connection revoked」「工具調用失敗」等。

**現狀**：`unity_common.task_reply_indicates_failure` 已加強；FAIL 時會印 **錯誤說明 + 助理回覆**（`run_build.py`）。

### 4. 設定檔格式混淆

| 用途 | 檔案 | 格式 |
|------|------|------|
| Cursor IDE | `%USERPROFILE%\.cursor\mcp.json` | `{ "mcpServers": { "name": { "command"/"url" } } }` |
| unity-mcp CLI | `unity_servers.json` | `{ "unity": { "transport", "command" 或 "url", ... } }` |

README 曾把 Cursor 的 `mcpServers` 範例寫成「複製到 unity_servers.json」，會導致載入失敗或缺 `transport`。

`load_server_specs` 現可 **unwrap `mcpServers`** 並推斷 `transport`，仍建議 CLI 用 aicentral 格式。

### 5. stdio relay vs HTTP

| 模式 | 設定 | 注意 |
|------|------|------|
| **stdio** | `relay_win.exe --mcp` | 本專案目前預設；需 Editor + relay Named Pipe；每次 list/ask 可能起子行程 |
| **http** | `http://localhost:8080/mcp` | 須在 Unity **內**啟動 HTTP Server；較適合長時間、避免 relay 生命週期問題 |

兩者 **不要混用同一個客戶端設定卻忘記改另一邊**（Cursor 用 HTTP、CLI 用 stdio 可以，但要各自設定正確）。

### 6. build_goals.yaml 欄位與程式

`goal`、`definition_of_done`、`execution_strategy`、`tasks[].objective` 需由 **`tasks.py`** 解析並注入 prompt（已實作）。僅寫在 YAML 而沒進 `system_context` / `prompt` 的內容，**不會**自動生效。

場景路徑請統一：**`Assets/_Scenes/ExampleScene.unity`**（勿用 `Assets/Scenes`）。

### 7. 日誌看不到「已確認資料夾」

**原因**：終端只印 **模型最後一篇文字**（且曾截斷 600 字），**不印** MCP tool 的 request/response。若模型只寫「嘗試」而未引用工具回傳，日誌裡就不會有「已確認 Assets/_Scenes」。

**處理**：`unity-mcp-build --json` 看完整 `reply`；或加大 prompt 要求「必須引用工具回傳」。

### 8. 沒有「部分達標」狀態

workflow 每任務只有 **OK / FAIL**（+ 啟發式文字判斷），**不會**程式化讀 Hierarchy 回報「有場景但缺燈光」。要分級驗收需另做工具查詢或專用驗證任務（如 `validate_scene`）。

---

## 建議的自建 Agent 流程

1. **連線**：`unity-mcp-list-tools --json` 成功再 build。
2. **模型**：MCP 建構用支援 **function calling** 的模型（必要時 `model: cloud-chat`）。
3. **核准**：Unity MCP 設定頁面先處理好，避免整輪 build 都在 revoked 上浪費 token。
4. **任務**：`build_goals.yaml` 一步一事；路徑固定 `Assets/_Scenes/`；最後 `validate_scene` 對照 `definition_of_done`。
5. **除錯**：失敗時 `--json`；單步 `unity-mcp-ask` 鎖定是 MCP 還是 LLM。
6. **Cursor**：`mcp.json` 與 `unity_servers.json` 分開維護；格式見 `docs/cursor-mcp.http.example.json`（HTTP）或 `unity_servers.stdio.example.json`（relay）。

---

## 常用指令

```powershell
cd c:\Users\PC\Documents\llm-server\unity-mcp

# 驗證 MCP（不呼叫 LLM）
unity-mcp-list-tools -c unity_servers.json --json

# 單步試工具 + 模型
unity-mcp-ask "請呼叫 unity__Unity_ManageGameObject 建立 TestCube" -c unity_servers.json

# 依 build_goals.yaml 順序建構
unity-mcp-build

# 完整回覆 JSON
unity-mcp-build --json
```

---

## `unity-mcp-list-tools` 成功但 `unity-mcp-build` 仍失敗？

**可以發生。** `list-tools` 只做 `list_tools`；`build` 會在 LLM 迴圈裡 **`call_tool`**（例如 `Unity_ListResources`）。

實測 log（stdio relay）：

```text
tool_call.execute toolName=Unity_ListResources
Error: Connection revoked. Go to Unity Editor > Project Settings > AI > Unity MCP to change approval.
```

表示：**連線已建立、工具列表可讀，但執行寫入/查詢類工具時仍被 Unity 核准機制擋下。** 請在 Editor 對 **執行 tool** 開放核准，而非僅連上 relay。

---

## 最近一次 build 結果（紀錄）

- 指令：`unity-mcp-build`（`build_goals.yaml` 六任務）
- 模型：`gemini-flash`（`build_goals.yaml`；需 `gemini.api_key`）
- 結果：第 1 步 `create_example_scene` → **FAIL**（Connection revoked on `Unity_ListResources`）
- 後續任務：因 `stop_on_error` 未執行

**下一步（人工）**：Unity → Project Settings → AI → Unity MCP → 核准 / Auto-approve → 再跑 `unity-mcp-build`。若模型仍不調工具，於 yaml 加 `model: cloud-chat`。

---

## 相關文件

- [專案 README](../README.md) — 快速開始
- [使用說明](README.md) — 呼叫鏈與 build_goals 欄位
- [BUILD.md](BUILD.md) — 建構工作流補充
