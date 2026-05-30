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

## 與 task_list.yaml 的分工

| 檔案 | 內容 | 更新時機 |
|------|------|----------|
| `task_list.yaml` | 任務隊列、status、verification、`pipeline_records` | 任務開始/結束（細粒度執行紀錄） |
| `project_state/` | 跨任務可讀的專案現況摘要（Markdown + 索引） | 任務**完成**後增量追加 |

規劃（Plan Normalize）與執行（`format_task_prompt`）會注入 `project_state` 摘要，並搭配 `task_list` 的 Harness 上下文。

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

## 更新規則

- **增量**：每任務完成追加 `tasks/<id>.md` 章節、更新 overview、寫入 `changelog.md`、更新 `_index.yaml`
- **記憶體緩衝**：`unity-mcp-harness` 整輪建構（`run_build_plan`）期間，更新先累積於 `ProjectStateSession`；**執行完成或中斷**時於 `finally` 一次 `flush` 落盤，減少每任務磁碟 IO
- **同輪後續任務**可透過記憶體索引與待寫入區塊取得最新摘要（無需等 flush）
- **非 ground truth**：標註於 prompt；Agent 仍須 Phase 1 MCP 讀取
- **失敗任務**也會記錄（status: failed），供後續規劃參考

## 手動編輯

可編輯 `scenes/_overview.md` 等補充說明；下次任務完成會**追加**章節，不會整檔覆寫（除非刪除檔案後由任務重建）。
