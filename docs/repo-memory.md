# Repo 核對摘要（2026-10-14）

本次為靜態閱讀核對；搭配根目錄 AGENTS.md 使用。程式與測試優先於舊文件。

## 已確認架構與流程

- Python 3.12 為 CI 與開發目標；src 為平面模組，以 asyncio、aiohttp、websockets、python-dotenv 組成服務。requirements-dev.txt 另加 pytest、Ruff；依賴使用最低版本限制，未鎖定精確版本。
- flash_service.py 同時啟動 Jin10／RSS 監控及 Telegram assistant；任一任務結束便取消其他任務。不要另開第二個 Telegram polling consumer。
- jin10_monitor.py：接收 → 有界佇列 → worker 關鍵字比對 → Gemini 分級 → 保存 → 相關性／門檻判斷 → Telegram。佇列滿丟最舊項目；MEDIUM／LOW 不保存。AI 失敗保留未分級背景、不推原文；保存不等於送達。
- feed_monitor.py 負責 HTTPS RSS/Atom 正規化與持久化去重；config 放新聞來源與 YouTube 頻道設定。data 是受版本控制的營運狀態，不是可清除的測試產物。
- daily_digest.py 從 archive 按 UTC+8 收錄日期選取已有摘要的 HIGH／CRITICAL，排除明確不相關資料，再呼叫 AI 彙整；沒有合格摘要不呼叫 AI，失敗不冒充成功。互動預設使用 live 配額，排程使用 digest 配額。
- yt_monitor.py 先保存發現的影片，分開記錄摘要、查證及逐段送達進度；摘要失敗保留重試，查證失敗可先送摘要再補查證。首次來源預熱不回播歷史。
- news_commands／telegram_assistant 提供查詢與問答；event_tracking 保存詞組追蹤及已讀進度；economic_calendar 獨立抓取經濟日曆；monitoring_metrics 記錄營運指標。
- workflows：快訊每 6 小時啟動、執行 350 分鐘；YouTube 每半小時、外層 24 分鐘；日報台灣 08:15、日曆 08:00。排程設定不代表實際準時或連續在線。
- persist-state action 將指定狀態提交回目前分支，push 衝突時重放自己的狀態；依賴每個檔案只有一個 writing workflow。送達與狀態提交不是交易，可能重複。

## 開發慣例與指令

先讀 CONTRIBUTING.md；修改行為時同步繁中／英文文件與相關離線測試，不順便全專案格式化。

```text
python -m venv .venv
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m pytest
python src/flash_service.py
```

最後一行為實際服務入口，可能推播。pytest 只收集 tests，並將 src 加入搜尋路徑；src/test_*.py 是外部服務診斷。Ruff 僅 E4/E7/E9/F。tests/conftest.py 使用暫存狀態、測試 Telegram 值及取消發送節流；新增測試也須隔離營運檔案。常數可能在 import 時載入，修改環境變數未必能改變已載入模組值。

## 文件落差與未確認事項

- docs/README.md 仍有「digest 最多八則、不增加模型呼叫」、「important 顯示來源摘錄」、獨立問答 workflow 等舊說明；以實作及 docs/daily-digest.md 為準。根 README 流程圖也將關鍵字過濾畫在佇列之前，且混入獨立 YouTube 流程。
- 本次未執行 pytest／Ruff，未驗證目前 Python／套件安裝、最新 CI、外部來源可用性、真實 Telegram 送達或 Gemini 配額。AGENTS.md 的 2026-10-07 環境限制僅為歷史紀錄。
- 本次未讀取 .env 或營運新聞內容、未啟動服務、未更動營運狀態。閱讀範圍包含專案指引、README／繁中文件、依賴、目錄、核心處理函式、測試 fixture 與 workflow／狀態回存實作；不是逐行完整程式稽核。
