# unity-mcp-harness CLI 速查

入口指令：`unity-mcp-harness`（建構與統一子命令）、`unity-mcp-list-tools`、`unity-mcp-ask`、`unity-mcp-chat`。

> **舊版 `unity-mcp-build` 已移除。** 請改裝 `unity-mcp-harness`（見下方「重新安裝」）。

## 統一入口（EXECUTE §12 — 已實作）

標記檔：`config/harness_capabilities.marker`（`tag: HARNESS_EXECUTE_12_IMPLEMENTED`）

| 參數 | 說明 |
|------|------|
| `--goals build` | `build_goals.yaml` → Plan Normalize → `task_list.yaml`（**只規劃**） |
| `--goals init` | 對話建立 `build_goals.yaml`（`/write` 覆寫） |
| `--goals modify` | 對話調整既有 tasks（`/write` 只更新 tasks） |
| `-g` / `--goals-file` | 藍圖路徑 |
| （無 `--goals`） | 依 `task_list.yaml` 執行 Unity MCP 建構 |
| `--tools` / `--tools json` | 列出 MCP 工具 |
| `--chat` | 探索 REPL |
| `--sync` | `task_list` → `build_goals` |
| `--status` | MCP 盤點 + `project_state` 同步 |

## 兩份 YAML 各是什麼

| 檔案 | 角色 |
|------|------|
| `build_goals.yaml` | 人類維護的**藍圖**（意圖、粗任務） |
| `task_list.yaml` | 執行期 **SSOT**（狀態、`pipeline_records`、`verification`） |

## 規劃與執行

| 指令 | 做什麼 | 會跑 Unity MCP？ |
|------|--------|------------------|
| `unity-mcp-harness --goals build` | 藍圖 → `task_list` | 否 |
| `unity-mcp-harness` | 執行 pending 任務（藍圖與隊列 id 不一致時會自動重算隊列） | 是 |

**順序阻擋**：若依 priority 排序的前置任務為 `failed`，後續 `pending` / `in_progress` **不會執行**，直到 `--retry-failed` 重試該 failed 項。

## 寫回 `build_goals.yaml`（進階）

| 參數 | 資料來源 |
|------|----------|
| `--export-goals-from-normalize` | LLM 規範化結果（搭配 `--goals build`） |
| `--export-goals-from-task-list` / `--sync` | `task_list` 規劃欄位 |

`--backup` 可與 export 合用（`build_goals.yaml.bak`）。

## 常見流程

```powershell
. .\scripts\_env.ps1

# 1. 改藍圖後更新執行隊列
unity-mcp-harness --goals build

# 2. 執行建構
unity-mcp-harness
```

## 舊參數（仍可用，會印警告 → 等同 `--goals build`，**不會**再自動執行建構）

| 舊 | 新 |
|----|-----|
| `--goals-to-task-list` / `--sync-plan` / `--replan` / `--init-tasks` / `--replan-and-run` | `--goals build` |

## 重新安裝（移除舊 pip 執行檔）

在 **已安裝過舊版** 的環境執行：

```powershell
pip uninstall -y unity-mcp-build
pip install -e .\unity-mcp-harness
```
