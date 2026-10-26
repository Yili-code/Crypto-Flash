# Telegram command menu

更新：2026-10-26（Asia/Taipei）
分支：main；基準：81887ee。
範圍：src/telegram_menu.py、src/telegram_assistant.py、中英文 README。
同步：本機舊的 YouTube quota 狀態保留至 .tmp/menu-sync-preserve，採用遠端較新的日期狀態，fast-forward 後 HEAD...origin/main=0/0。其他未追蹤 handoff 保留。
決策：menu 僅放無必要參數的常用指令；不移除 command handlers。啟動更新失敗不阻止 polling。
已實作：七個 one-tap commands 與啟動註冊、手動更新入口。
已驗證：Ruff 通過；50 項相關離線測試通過。Telegram setMyCommands 成功，getMyCommands 讀回與 MENU_COMMANDS 完全一致。受限環境 asyncio 停滯，改於獲准環境執行。
限制：已更新 Telegram 預設選單，未逐一處理其他 scope/language 的既有覆寫；未從 Telegram client 截圖確認。
commit/push：準備提交本任務檔案並推送 origin/main；未部署雲端服務。
