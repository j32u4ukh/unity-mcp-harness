# Unity 專案狀態文件樹

此目錄位於 **Harness 外部工作區**（`UNITY_MCP_HOME/project_state/`），與 `task_list.yaml` 搭配使用。

## 用途

- **累積** Unity 專案已知現況（場景、資產、系統），供 Plan Normalize 與執行 Agent 參考
- **增量更新**：Harness 在每個任務完成後追加/更新對應分項，不會一次寫滿全貌
- **非 ground truth**：Editor 可能已變更；執行前仍須 MCP Phase 1 讀取驗證

## 結構

| 路徑 | 說明 |
|------|------|
| `_index.yaml` | 樹狀索引（路徑、一行摘要、最後更新任務） |
| `changelog.md` | 變更流水帳 |
| `scenes/_overview.md` | 場景 / Hierarchy 摘要 |
| `assets/_overview.md` | 資產與生成物摘要 |
| `systems/_overview.md` | 相機、光照、URP 等系統摘要 |
| `tasks/<task_id>.md` | 各任務完成後的詳細紀錄（自動建立） |

## 維護

- 首次由 `unity-mcp-harness --init` 建立空範本
- 執行 `unity-mcp-harness` / `.\scripts\harness-run.ps1` 時自動更新
- 可手動編輯補充；下次任務完成會追加章節，不會整檔覆寫
