# unity-mcp-harness CLI 速查

入口指令：`unity-mcp-harness`（建構）、`unity-mcp-list-tools`、`unity-mcp-ask`、`unity-mcp-chat`。

> **舊版 `unity-mcp-build` 已移除。** 請改裝 `unity-mcp-harness`（見下方「重新安裝」）。

## 兩份 YAML 各是什麼

| 檔案 | 角色 |
|------|------|
| `build_goals.yaml` | 人類維護的**藍圖**（意圖、粗任務） |
| `task_list.yaml` | 執行期 **SSOT**（狀態、`pipeline_records`、`verification`） |

## 規劃與執行（新參數）

| 參數 | 做什麼 | 會跑 Unity MCP？ |
|------|--------|------------------|
| `--goals-to-task-list` | `build_goals` → Plan Normalize → 更新 `task_list` | 否 |
| `--replan-and-run` | 同上，然後執行 pending 任務 | 是 |
| （無旗標，已有 `task_list`） | 只執行隊列，**不**自動重讀藍圖 | 是 |

## 寫回 `build_goals.yaml`（勿混用）

| 參數 | 資料來源 | 必須搭配 |
|------|----------|----------|
| `--export-goals-from-normalize` | LLM **規範化結果** | 通常 `--replan-and-run` 或首次建隊列 |
| `--export-goals-from-task-list` | **`task_list` 規劃欄位** | 單獨指令即可（不需 LLM） |

`--backup` 可與任一 export 合用（寫回前產生 `build_goals.yaml.bak`）。

## 常見流程

```powershell
# 工作區
. .\scripts\_env.ps1

# 1. 改藍圖後，只更新執行隊列
.\scripts\harness-goals-to-task-list.ps1

# 2. 執行（不重規劃）
.\scripts\harness-run.ps1

# 改藍圖後要「重算隊列 + 立刻開工」
unity-mcp-harness --replan-and-run
```

## 舊參數對照（仍可用，會印警告）

| 舊 | 新 |
|----|-----|
| `--sync-plan` | `--goals-to-task-list` |
| `--replan` | `--replan-and-run` |
| `--write-back-goals`（搭配 sync-plan） | `--goals-to-task-list --export-goals-from-task-list` 或單獨 `--export-goals-from-task-list` |
| `--write-back-goals`（搭配 replan） | `--replan-and-run --export-goals-from-normalize` |

## 重新安裝（移除舊 pip 執行檔）

在 **已安裝過舊版** 的環境執行：

```powershell
# 1. 解除安裝套件（會移除 Scripts 下的 unity-mcp-build.exe 等）
pip uninstall unity-mcp-harness -y

# 2. 確認已無殘留（應顯示 WARNING: Package(s) not found 或成功）
pip show unity-mcp-harness

# 3. 可選：刪除仍留在 PATH 的殘檔（若 pip uninstall 後仍存在）
$scripts = python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
Get-ChildItem $scripts -Filter "unity-mcp-*" | Select-Object Name, LastWriteTime

# 4. 從原始碼目錄 editable 安裝
cd C:\Users\PC\Documents\llm-server\unity-mcp-harness
pip install -e .

# 5. 確認入口（應有 harness，不應再依賴 unity-mcp-build）
Get-ChildItem $scripts -Filter "unity-mcp-*"
unity-mcp-harness --help
```

若曾用 PyInstaller 打包的 `unity-mcp-build.exe`，請手動刪除 `dist\` 內舊 exe，與 pip 無關。
