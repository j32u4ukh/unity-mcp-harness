# Unity 專案狀態文件樹（project_state/）

## 位置

位於 **外部 Harness 工作區** 根目錄：

```
UNITY_MCP_HOME/
  build_goals.yaml
  task_list.yaml          # 執行期 SSOT（任務狀態、pipeline_records）
  project_state/          # Unity 專案累積認知（本文件）
    _index.yaml
    changelog.md
    scenes/_overview.md
    assets/_overview.md
    systems/_overview.md
    tasks/<task_id>.md
```

與 Unity 遊戲專案（`config/local.env.ps1` 內路徑）**分離**；不寫入 `Assets/`。

## 與 task_list.yaml 的分工（SSOT 優先序）

| 來源 | 角色 |
|------|------|
| `task_list.yaml` | **執行 SSOT**：status、verification、`pipeline_records` / `harness_verification` |
| `project_state/` | **對外摘要**：`tasks/<id>.md` 的 `## 當前狀態`、`_index.yaml`、`## 當前快照` overview |
| `changelog.md` | 稽核流水（追加，不刪舊行） |
| `--bootstrap-state` MCP 盤點 | 場景/資產基線快照（可選） |

**原則**：僅 `status=completed` 且 `verification` 為 `verified` / `skipped_by_idempotent` 才可視為藍圖子項已完成。`failed` / `pending` 必須出現在規劃輸入中；Agent 樂觀回覆僅能作「未採信」附註，不得寫入索引主摘要。

規劃（Plan Normalize）會注入 **task_list SSOT 表** + 同步後的 `project_state` 索引；與 SSOT 衝突的備忘一律忽略。

## 建立

`unity-mcp-harness --init` 會複製空範本目錄與占位文件。

既有工作區可再執行一次 `--init`（已存在檔案會 skip，僅補 `project_state/`）。

## 初始化狀態樹（既有 Unity 專案）

在 `--init` 並設定 `config/secret.yaml`、`config/local.env.ps1`、啟動 Unity Editor 後：

```powershell
unity-mcp-harness --bootstrap-state
# 或
.\scripts\bootstrap-state.ps1
```

- **唯讀** MCP 盤點現場，寫入 `project_state/`（含 `tasks/bootstrap_state.md`、各 overview）
- **不**修改 `task_list.yaml`、**不**跑 Plan Normalize / LangGraph
- 自訂盤點問題：`--bootstrap-prompt "你的問題"`
- 預設 prompt 來自 `config/unity_explore.yaml` 的 `probe_prompt`（若存在）

建議順序：`--init` → 編輯設定 → `--bootstrap-state` → 編輯 `build_goals.yaml` → `harness-dry-run --replan` → `harness-run`。

## 同步與修剪（`--sync-project-state`）

依 `task_list.yaml` 重建 `project_state`（修剪舊 `## 任務 …` 章節，只保留標題 + `## 當前狀態` + changelog 稽核）：

```powershell
unity-mcp-harness --sync-project-state
```

**自動同步時機**：

- `prepare_harness_queue` 載入/建立 `task_list` 後
- `run_build_plan` 結束 `end_session(flush=True)` 後全量校正 index/overview

**修復過期備忘現場**（例如 Normalize 誤判已完成）：

1. `--sync-project-state`
2. 可選：`--bootstrap-state` 刷新場景 `## 當前快照`
3. `--goals-to-task-list` 或 `--replan` 檢查隊列是否仍含 `failed` / `pending`

## 更新規則

- **任務檔**：每任務結束**覆寫** `tasks/<id>.md` 的 `## 當前狀態`（由 SSOT 摘要生成，非無限追加 `## 任務`）
- **changelog**：仍追加一行（稽核）
- **索引 / overview 快照**：全量 sync 或建構結束時依 verified 任務彙整 `## 當前快照`
- **記憶體緩衝**：整輪建構期間先累積於 `ProjectStateSession`，`finally` flush 後再全量 sync 校正
- **失敗任務**：索引摘要含 `failed`，不以 Agent「已成功」為主語

## 手動編輯

可編輯 overview 的 `## 當前快照` 補充說明；下次 `--sync-project-state` 或建構結束 sync 會依 task_list 覆寫快照區塊。`changelog.md` 僅追加、不自動刪行。
