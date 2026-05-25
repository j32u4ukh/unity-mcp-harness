# 打包為執行檔（unity-mcp-build.exe）

## 為何要打包

Unity **Project Settings → AI → Unity MCP** 會依「客戶端」要求核准。若每次用不同的 `python.exe`、虛擬環境或工作目錄啟動，Editor 可能反覆要求允許。

使用**固定路徑**的 `unity-mcp-build.exe`，在 Unity 內核准一次（或開啟 Auto-approve）後，之後執行通常不必再按。

> stdio 模式下實際連 Editor 的是 `relay_win.exe`（見 `unity_servers.json`），與外層是 python 或 exe 無關；若仍常出現 Connection revoked，請在 Unity 開啟自動核准。

## 什麼不用重新編譯

下列皆在**執行時**讀取，改完存檔後直接再跑 exe 即可：

| 檔案 / 來源 | 內容 |
|-------------|------|
| `build_goals.yaml`（或 `-g` / `UNITY_BUILD_GOALS`） | 任務清單、`goal`、`definition_of_done`、`execution_strategy`、`tasks[]`、`model`、`enabled` |
| `unity_servers.json`（或 `-c` / `UNITY_MCP_CONFIG`） | Unity MCP 連線（stdio relay / HTTP） |
| `config/secret.yaml`（aicentral） | LLM API 金鑰 |
| `config/aicentral.yaml`（可選） | 模型別名、Gemini 池等 |

程式邏輯（LangGraph 編排、prompt 組裝）才需要重新打包。

## 建置

```powershell
cd unity-mcp
pip install -e .
pip install pyinstaller
.\scripts\build_exe.ps1
```

產物：`dist\unity-mcp-build\unity-mcp-build.exe`

## 部署目錄建議

```
my-unity-build\
  unity-mcp-build.exe
  build_goals.yaml          ← 編輯任務
  unity_servers.json        ← MCP 連線
  config\
    secret.yaml             ← 從 aicentral 複製
    aicentral.yaml          ← 可選
```

或設環境變數：

- `UNITY_MCP_HOME` → 放 yaml/json 的目錄
- `AICENTRAL_HOME` → aicentral 專案根（內含 `config/`）

## 執行

```powershell
cd my-unity-build
.\unity-mcp-build.exe
.\unity-mcp-build.exe --dry-run
.\unity-mcp-build.exe -g D:\plans\other_goals.yaml
```

## 與原始碼開發的差異

| | `unity-mcp-build`（pip） | `unity-mcp-build.exe` |
|--|--------------------------|------------------------|
| 工作目錄 | `unity-mcp` 專案根 | exe 所在目錄（或 `UNITY_MCP_HOME`） |
| aicentral 設定 | `../aicentral/config/` | exe 旁 `config/` 或 `AICENTRAL_HOME` |
