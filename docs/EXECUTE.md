# unity-mcp-harness 實際執行指令（操作順序版）

以下按「實際操作時間線」排列，照順序執行即可。

---

## 1) 一次性安裝（首次才做）

```powershell
cd ..\aicentral
Copy-Item config\secret.yaml.example config\secret.yaml
# 在 secret.yaml 填入 gemini.api_key
pip install -e ".[mcp]"

cd ..\unity-mcp-harness
pip install -e .
```

---

## 2) 準備專案檔案（每個專案至少做一次）

```powershell
cd c:\Users\PC\Documents\llm-server\unity-mcp-harness
Copy-Item build_goals.example.yaml build_goals.yaml
# 編輯 build_goals.yaml（你的任務定義）
```

如果你用 stdio relay（預設）：

```powershell
Copy-Item unity_servers.stdio.example.json unity_servers.json
```

如果你用 HTTP MCP：

```powershell
Copy-Item unity_servers.example.json unity_servers.json
```

---

## 3) 啟動 Unity（擇一）

### 3.1 手動開 Unity Editor

直接開啟你的 Unity 專案（一般互動模式）。

### 3.2 用批次腳本啟動（batch mode）

```powershell
.\scripts\start_batch_unity.ps1
```

指定 Unity 版本或專案路徑：

```powershell
.\scripts\start_batch_unity.ps1 -UnityExe "C:\Program Files\Unity\Hub\Editor\6000.4.8f1\Editor\Unity.exe" -ProjectPath "C:\Users\PC\Documents\UnityProjects\PlanetaryMalignancy"
```

---

## 4) 執行前檢查（確認 MCP 真的可用）

```powershell
unity-mcp-list-tools --json
```

看到工具列表再進下一步。

---

## 5) 主要建構流程

### 5.1 先看計畫（不動 Unity）

```powershell
unity-mcp-harness --dry-run
```

### 5.2 正式執行

```powershell
unity-mcp-harness
```

---

## 6) 執行中的常用操作

### 6.1 失敗也繼續後續任務

```powershell
unity-mcp-harness --continue-on-error
```

### 6.2 輸出完整 JSON（含 verification）

```powershell
unity-mcp-harness --json
```

### 6.3 中斷後續跑 failed 任務

```powershell
unity-mcp-harness --retry-failed
```

### 6.4 藍圖改完後同步 task_list

```powershell
unity-mcp-harness --sync-plan
```

若要把目前規劃欄位寫回 `build_goals.yaml`：

```powershell
unity-mcp-harness --sync-plan --write-back-goals --backup
```

### 6.5 強制重新規劃（重建 task_list）

```powershell
unity-mcp-harness --replan
```

---

## 7) 快速除錯

單次提問：

```powershell
unity-mcp-ask "請列出目前可用的 Unity MCP 工具並說明可建立哪些場景物件"
```

互動模式：

```powershell
unity-mcp-chat
```

---

## 8) 結束後關閉 Unity（若你使用 batch 腳本啟動）

```powershell
.\scripts\finish_batch_unity.ps1
```

---

## 9) 打包成執行檔（可選，通常在流程穩定後）

安裝 PyInstaller 並打包：

```powershell
pip install pyinstaller
.\scripts\build_exe.ps1
```

產物位置：

```text
dist\unity-mcp-build\unity-mcp-build.exe
```

將下列檔案放到 exe 同層後執行：

- `build_goals.yaml`
- `unity_servers.json`
- `config\secret.yaml`（可選再放 `config\aicentral.yaml`）

執行方式：

```powershell
cd .\dist\unity-mcp-build
.\unity-mcp-build.exe --dry-run
.\unity-mcp-build.exe
```

---

## 10) 相容別名

`unity-mcp-build` 與 `unity-mcp-harness` 等價，可替換使用。
