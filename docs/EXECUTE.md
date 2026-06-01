# unity-mcp-harness 實際執行指令（操作順序版）

以下改成命令提示字元呈現（`PS 目前目錄> 指令`），可直接對照你終端機狀態。

**路徑約定**：

- **引擎開發**：repo 根目錄 `llm-server/`，Harness 原始碼在 `unity-mcp-harness/`
- **外部工作區（推薦）**：任意目錄 + `UNITY_MCP_HOME`；以 `unity-mcp-harness --init` 建立（見 [EXTERNAL_PROJECT.md](EXTERNAL_PROJECT.md)）

```text
llm-server/
├── aicentral/
├── unity-mcp-harness/    ← Harness 引擎（pip 安裝）
└── planetary-malignamcy/ ← 範例外部工作區（--init 產物）
```

---

## 1) 一次性安裝（首次才做）

```powershell
PS llm-server> cd .\aicentral
PS aicentral> Copy-Item .\config\secret.yaml.example .\config\secret.yaml
PS aicentral> # 在 secret.yaml 填入 gemini.api_key
PS aicentral> pip install -e ".[mcp]"

PS aicentral> cd ..\unity-mcp-harness
PS unity-mcp-harness> pip install -e .
```

安裝後確認 CLI 已註冊（應列出 `unity-mcp-harness.exe`）：

```powershell
PS unity-mcp-harness> python -m pip show unity-mcp-harness
PS unity-mcp-harness> Get-ChildItem "$(python -c "import sysconfig; print(sysconfig.get_path('scripts'))")" -Filter "unity-mcp*"
PS unity-mcp-harness> unity-mcp-harness --help
```

若出現 **`無法辨識 'unity-mcp-harness'`**（`CommandNotFoundException`）：

| 原因 | 處理 |
|------|------|
| 尚未 `pip install -e .` | 在 `unity-mcp-harness` 目錄重新安裝 |
| 安裝過舊、沒有 `unity-mcp-harness` 入口 | 再執行一次 `pip install -e .` |
| Python `Scripts` 不在 PATH | 依下方方式暫時加入 |

**PATH 未包含 Scripts（Windows 常見）**：

```powershell
PS unity-mcp-harness> $scripts = python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
PS unity-mcp-harness> $env:Path = "$scripts;$env:Path"
PS unity-mcp-harness> unity-mcp-harness --help
```

或不用改 PATH，直接跑 Python 模組：

```powershell
PS unity-mcp-harness> python .\run_build.py --dry-run
PS unity-mcp-harness> python .\run_build.py
PS unity-mcp-harness> python .\unity_mcp_list_tools.py --json
```

---

## 2) 準備專案檔案（每個專案至少做一次）

```powershell
PS llm-server> cd .\unity-mcp-harness
PS unity-mcp-harness> Copy-Item .\build_goals.example.yaml .\build_goals.yaml
PS unity-mcp-harness> # 編輯 .\build_goals.yaml
```

stdio relay（預設）：

```powershell
PS unity-mcp-harness> Copy-Item .\unity_servers.stdio.example.json .\unity_servers.json
```

HTTP MCP：

```powershell
PS unity-mcp-harness> Copy-Item .\unity_servers.example.json .\unity_servers.json
```

---

## 3) 啟動 Unity（擇一）

### 3.1 手動開 Unity Editor

直接開啟你的 Unity 專案（一般互動模式）。

### 3.2 用批次腳本啟動（batch mode）

```powershell
PS llm-server> cd .\unity-mcp-harness
PS unity-mcp-harness> .\scripts\start_batch_unity.ps1
```

指定 Unity 版本或專案路徑：

```powershell
PS unity-mcp-harness> .\scripts\start_batch_unity.ps1 -UnityExe "C:\Program Files\Unity\Hub\Editor\6000.4.8f1\Editor\Unity.exe" -ProjectPath "C:\Users\PC\Documents\UnityProjects\PlanetaryMalignancy"
```

---

## 4) 執行前檢查（確認 MCP 真的可用）

```powershell
PS llm-server> cd .\unity-mcp-harness
PS unity-mcp-harness> unity-mcp-list-tools --json
PS unity-mcp-harness> # 若 CLI 不在 PATH：python .\list_tools.py --json
```

看到工具列表再進下一步。

---

## 5) 主要建構流程

### 5.1 先看計畫（不動 Unity）

```powershell
PS llm-server> cd .\unity-mcp-harness
PS unity-mcp-harness> unity-mcp-harness --dry-run
PS unity-mcp-harness> # 若 CLI 不在 PATH：python .\run_build.py --dry-run
```

### 5.2 正式執行

```powershell
PS unity-mcp-harness> unity-mcp-harness
PS unity-mcp-harness> # 若 CLI 不在 PATH：python .\run_build.py
```

---

## 6) 執行中的常用操作

以下皆在 `unity-mcp-harness` 目錄執行（CLI 不可用時，將 `unity-mcp-harness` 換成 `python .\run_build.py`）。

### 6.1 失敗也繼續後續任務

```powershell
PS unity-mcp-harness> unity-mcp-harness --continue-on-error
```

### 6.2 輸出完整 JSON（含 verification）

```powershell
PS unity-mcp-harness> unity-mcp-harness --json
```

### 6.3 中斷後續跑 failed 任務

```powershell
PS unity-mcp-harness> unity-mcp-harness --retry-failed
```

### 6.4 藍圖 → task_list（只規劃，不跑 Unity）

```powershell
PS planetary-malignamcy> unity-mcp-harness --goals build
# 或
PS planetary-malignamcy> .\scripts\harness-goals-to-task-list.ps1
```

來源：`build_goals.yaml` → 目標：`task_list.yaml`（保留仍對應藍圖 id 的 `completed` 紀錄）。

預覽不寫檔：`unity-mcp-harness --goals build --dry-run`

若要把 **`task_list` 的規劃欄位** 寫回藍圖：`unity-mcp-harness --sync --backup`

### 6.5 依 task_list 執行建構

```powershell
PS planetary-malignamcy> unity-mcp-harness
# 或
PS planetary-malignamcy> .\scripts\harness-run.ps1
```

**不帶** `--goals` 才會連 Unity MCP。改藍圖後請先 `--goals build`，再執行本節指令。

完整旗標說明見 [CLI.md](CLI.md)。

---

## 7) Unity 專案探索（非純 LLM 聊天）

與 `aicentral-chat` 不同，`unity-mcp-chat` / `unity-mcp-ask` **必須連線 Unity MCP**，並以工具查詢 Editor 內真實現況後再回答。行為可由 `config/unity_explore.yaml` 調整。

前置：Unity Editor 已開啟，且 `unity-mcp-list-tools --json` 可列出工具。

單次探索：

```powershell
PS llm-server> cd .\unity-mcp-harness
PS unity-mcp-harness> unity-mcp-ask "Example2DScene 場景中的 Sprite 資產叫什麼？"
PS unity-mcp-harness> unity-mcp-ask --probe
```

多輪探索（啟動時預設做一次唯讀現況探查；REPL 支援 `/tools`、`/status`、`/help`）：

```powershell
PS unity-mcp-harness> unity-mcp-chat
PS unity-mcp-harness> unity-mcp-chat --no-probe
```

LLM 設定預設讀取本專案 `config/aicentral.yaml` 與 `config/secret.yaml`（**不是** `aicentral/config/`）。
可用 `--aicentral-config`、`--secret` 覆寫；Unity MCP 連線用 `-c` / `--unity-config`（`unity_servers.json`）。

```powershell
PS unity-mcp-harness> unity-mcp-ask "Example2DScene 的 Sprite 叫什麼？" --secret .\config\secret.yaml
```

---

## 8) 快速除錯（建構流程）

若僅需確認 MCP 連線：

```powershell
PS unity-mcp-harness> unity-mcp-list-tools --json
```

---

## 9) 結束後關閉 Unity（若你使用 batch 腳本啟動）

```powershell
PS llm-server> cd .\unity-mcp-harness
PS unity-mcp-harness> .\scripts\finish_batch_unity.ps1
```

---

## 10) 打包成執行檔（可選，通常在流程穩定後）

安裝 PyInstaller 並打包：

```powershell
PS llm-server> cd .\unity-mcp-harness
PS unity-mcp-harness> pip install pyinstaller
PS unity-mcp-harness> .\scripts\build_exe.ps1
```

產物位置（相對 Harness 目錄）：

```text
.\dist\unity-mcp-build\unity-mcp-build.exe
```

將下列檔案放到 exe 同層後執行：

- `.\build_goals.yaml`
- `.\unity_servers.json`
- `.\config\secret.yaml`（可選再放 `.\config\aicentral.yaml`、`.\config\unity_explore.yaml`）

執行方式：

```powershell
PS unity-mcp-harness> cd .\dist\unity-mcp-build
PS unity-mcp-build> .\unity-mcp-build.exe --dry-run
PS unity-mcp-build> .\unity-mcp-build.exe
```

---

## 11) 相容別名

舊版 `unity-mcp-build` 已移除；請見 [CLI.md](CLI.md) 的重新安裝步驟。


--- 

## 12) 調整規劃

<!-- ✅ HARNESS_EXECUTE_12_IMPLEMENTED — 見 config/harness_capabilities.marker -->

```
unity-mcp-harness --goals [build|init|modify]
```

> **已實作**（2026-05）：下列子指令已掛入 `unity-mcp-harness`；完成後會寫入 `config/harness_capabilities.marker`（`tag: HARNESS_EXECUTE_12_IMPLEMENTED`）。藍圖路徑改為 `-g` / `--goals-file`（原 `-g` 僅路徑時請改用 `--goals-file`）。

- build: 預設值，行為與目前相同，是將 build_goals.yaml 轉換成 task_list.yaml，沒設置參數的話也使用這個。

- init: 開啟對話模式，與使用者討論此次 build_goals.yaml 內容，減少讓人手動編輯 build_goals.yaml 的部分。
    - 首先要定義此次任務的一個里程碑（之後提問**僅收斂**於里程碑內，不向外擴散新系統）
    - 討論涉及**現有**腳本/場景/資產時，Harness 會透過 **Unity MCP 唯讀**查證（需 Editor + MCP Server）；可用 `/mcp 你的問題` 強制查詢
    - unity-mcp-harness 根據該里程碑列出數項子目標，針對模糊處做 1～3 個具體問題
    - 結束討論後輸入 `/write`，輸出符合規範的 build_goals.yaml，覆蓋原有內容

- modify: 開啟對話模式，針對 build_goals.yaml 現有項目作調整。
    - 印出目前的子目標描述，帶有編號方便後續討論
    - 選擇要討論的子目標後，印出更多的描述，並和我討論該項目標有無問題，是否該細分等
    - 會對現有 build_goals.yaml 的子目標做增減或調整描述
    - 不會直接覆蓋整個 build_goals.yaml

```
unity-mcp-harness --tasks [run|modify]
```

- run: 執行 task_list.yaml 當中的任務，效果同原本的 `unity-mcp-harness`，原本的 `unity-mcp-harness` 應該印出類似 --help 的效果

- modify: 開啟對話模式，針對 task_list.yaml 現有任務描述作調整。
    - 印出目前的子目標描述，帶有編號方便後續討論
    - 選擇要討論的子目標後，印出更多的描述，並和我討論該項目標有無問題，是否該細分等
    - 會對現有 task_list.yaml 的子目標做增減或調整描述
    - 不會直接覆蓋整個 task_list.yaml
    - 一樣應具備調用 MCP 的能力，針對專案實際情況進行討論

```
unity-mcp-harness --tools
unity-mcp-harness --tools json
```

- 取代原 unity-mcp-list-tools [|--json] 指令（舊指令仍可用）

```
unity-mcp-harness --chat
```

- 取代原 unity-mcp-chat 指令

```
unity-mcp-harness --sync
```

- 將 task_list.yaml 寫回 build_goals.yaml，原本轉換過程中，如果 AGENT 認定需要新增或減少幾項更加明確的任務，目標數和任務數可能發生偏離。執行期間也可能針對實際任務描述的 task_list.yaml 做手動修改，此指令幫我將 task_list.yaml 寫回 build_goals.yaml，由於是目標，所以不會像實際任務描述的那個詳細，但可以確保下一次再利用 build_goals.yaml 生成 task_list.yaml 的時候，不會落差太大。


```
unity-mcp-harness --status
```

- 針對目前場景中的狀態，對狀態數文件做全面更新
