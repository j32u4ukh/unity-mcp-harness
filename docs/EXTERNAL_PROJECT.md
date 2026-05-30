# 外部 Harness 工作區

Harness **引擎**（`unity-mcp-harness` pip 套件）與 **工作區**（設定、藍圖、執行期狀態）分離。每個 Unity 遊戲專案可擁有獨立工作區，以 `UNITY_MCP_HOME` 指向其根目錄。

## 三層分離

| 層 | 內容 | 位置 |
|----|------|------|
| 引擎 | CLI、LangGraph、scaffold 範本 | `pip install unity-mcp-harness` |
| 工作區 | `build_goals.yaml`、`config/`、`task_list.yaml` | 任意目錄（`UNITY_MCP_HOME`） |
| Unity 專案 | 場景、資產、Editor | `config/local.env.ps1` 內絕對路徑 |

## 一鍵初始化

```powershell
# 安裝引擎（開發期）
pip install -e C:\path\to\unity-mcp-harness

# 建立工作區（目前目錄）
mkdir C:\path\to\my-game-harness
cd C:\path\to\my-game-harness
unity-mcp-harness --init

# 或指定路徑
unity-mcp-harness --init C:\path\to\my-game-harness
```

`--init` 會：

- 複製 scaffold 範本（`*.example` → 實際檔名）
- 建立 `scripts/`（`_env.ps1`、Unity 啟停、Harness 包裝）
- **不**建立 `task_list.yaml`（首次 `--replan` 時產生）
- **立即 exit**，不載入 secret、不連 MCP、不跑 LangGraph

### 旗標

| 旗標 | 說明 |
|------|------|
| `--init-force` | 覆寫已存在檔案（含 `config/secret.yaml`，請謹慎） |
| `--init-http` | 使用 HTTP MCP 範本（預設 stdio relay） |

`--init` 與 `--init-tasks` 不同：`--init-tasks` 從既有 `build_goals.yaml` bootstrap `task_list.yaml`，需在工作區內且已有藍圖。

## 初始化後目錄

```
my-game-harness/          # UNITY_MCP_HOME
  README.md
  build_goals.yaml
  unity_servers.json
  .gitignore
  config/
    secret.yaml           # 填 api_key
    aicentral.yaml
    prompt_supplements.json
    unity_explore.yaml
    project.yaml
    local.env.ps1         # Unity 絕對路徑
  scripts/
    _env.ps1
    start-unity.ps1
    harness-run.ps1
    ...
  project_state/          # Unity 狀態文件樹（--init 建立，執行後自動更新）
    _index.yaml
    scenes/_overview.md
    tasks/<task_id>.md
  # task_list.yaml        # --replan 後產生
```

詳見 [PROJECT_STATE.md](PROJECT_STATE.md)。

## 典型 onboarding

```powershell
# 1. 編輯機密與本機路徑
notepad config\secret.yaml
notepad config\local.env.ps1

# 2. 啟動 Unity + 驗證 MCP（scripts 會自動設定 UNITY_MCP_HOME）
.\scripts\start-unity.ps1
.\scripts\list-tools.ps1

# 3. 盤點既有專案 → project_state/（接手已存在 Unity 專案時建議）
.\scripts\bootstrap-state.ps1

# 4. 規劃 + 執行
.\scripts\harness-dry-run.ps1
.\scripts\harness-run.ps1
```

`--bootstrap-state` 詳見 [PROJECT_STATE.md](PROJECT_STATE.md)。

直接跑 CLI 時，請先 `. .\scripts\_env.ps1` 或 `$env:UNITY_MCP_HOME = (Get-Location).Path`。

## 環境變數

| 變數 | 用途 |
|------|------|
| `UNITY_MCP_HOME` | 工作區根目錄（`build_goals.yaml`、`config/`、`task_list.yaml`） |
| `AICENTRAL_HOME` | 通常不必設；預設讀 `UNITY_MCP_HOME/config` |

## 重新補齊範本

```powershell
unity-mcp-harness --init
# 或
.\scripts\setup.ps1
```

已存在檔案預設略過；`config/secret.yaml` 除非 `--init-force` 否則永不覆寫。

## 範例：planetary-malignamcy

```powershell
unity-mcp-harness --init C:\Users\PC\Documents\llm-server\planetary-malignamcy
cd C:\Users\PC\Documents\llm-server\planetary-malignamcy
# 編輯 config\secret.yaml、config\local.env.ps1
.\scripts\harness-dry-run.ps1
```

Unity 遊戲專案路徑範例：`C:\Users\PC\Documents\UnityProjects\PlanetaryMalignancy`
