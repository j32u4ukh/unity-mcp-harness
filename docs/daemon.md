改寫 Python，讓進程變成「常駐型守護行程（Daemon / Persistent）」

這是目前做 AI Agent 連接 Unity 最正規的工程寫法。

    不要讓你的 Python unity-mcp-build.exe 每做完一個步驟就關閉。

    做法：改寫 Python 核心，讓它啟動後進入一個無窮迴圈（如 while True 監聽），在同一次執行（同一個 PID）當中，一口氣把這 6 個任務全部執行完。

    只要進程在整個建構工作流期間不宣告死亡，Unity 偵測到是同一個連接渠道、同一個 PID，你就只需要在開天闢地第一步點擊 一次 Allow，後面的 5 個步驟就會像絲般順滑地自動跑完！