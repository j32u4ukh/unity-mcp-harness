# Unity MCP Harness 工作區

此目錄為 **外部 Harness 工作區**（`UNITY_MCP_HOME`），與 Unity 遊戲專案分離。Harness 引擎（`unity-mcp-harness` CLI）讀取此處的藍圖與設定。

## 首次設定

1. 編輯 `config/secret.yaml` — 填入 `gemini.api_key`（及其他 provider 若需要）
2. 編輯 `config/local.env.ps1` — 填入本機 Unity 專案與 Editor 絕對路徑
3. 確認 `unity_servers.json` 連線方式（預設 stdio relay）

## 典型流程（推薦：scripts 會自動設定 UNITY_MCP_HOME）

```powershell
cd <工作區根目錄>

# 驗證 MCP 連線
.\scripts\list-tools.ps1

# 規劃（不執行建構）
.\scripts\harness-dry-run.ps1

# 執行建構
.\scripts\harness-run.ps1
```

## 直接使用 CLI（可選）

需先在本機 session 設定工作區根目錄，擇一即可：

```powershell
. .\scripts\_env.ps1
# 或
$env:UNITY_MCP_HOME = (Get-Location).Path
```

之後可直接呼叫：

```powershell
unity-mcp-harness --dry-run --replan
unity-mcp-harness
```

## 檔案說明

| 檔案 | 用途 |
|------|------|
| `build_goals.yaml` | 建構藍圖（人類維護） |
| `task_list.yaml` | 執行期 SSOT（首次 `--replan` 後產生） |
| `unity_servers.json` | Unity MCP 連線 |
| `config/aicentral.yaml` | LLM 模型別名與 gemini 池 |
| `config/prompt_supplements.json` | 規劃／執行 prompt 補充 |
| `project_state/` | Unity 專案狀態文件樹（與 `task_list.yaml` 搭配；執行後自動更新） |

詳見 Harness 引擎 repo 的 `docs/EXTERNAL_PROJECT.md` 與 `docs/PROJECT_STATE.md`。

## 重新初始化

若需補齊缺少的範本檔（不覆寫既有檔）：

```powershell
unity-mcp-harness --init
```

強制覆寫（**含 secret.yaml，請謹慎**）：

```powershell
unity-mcp-harness --init --init-force
```
