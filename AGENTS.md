<!-- BEGIN CODEX CROSS-SESSION SYNC -->
## 多對話與跨電腦交接（2026-10-21）

這一節是目前的交接規則；下方有日期的舊摘要保留作歷史導覽，不能當成目前進度。使用者最新明確指示優先。

### 每次開始或恢復工作
- 先確認本次 SessionStart / UserPromptSubmit hook 的同步結果。若未執行，從專案根目錄執行 `python .codex/session_sync.py --manual`（macOS/Linux 可用 python3）。
- hook 只 fetch 並在工作目錄乾淨且歷史可快轉時更新追蹤分支。不會 commit、push、stash、reset 或覆蓋衝突。
- 同步失敗、遠端領先且本機有修改、歷史分歧時，先處理同步問題；可做唯讀診斷，不可把狀態說成已同步。離線工作需明確標記。
- 同步後重新讀取本檔、PROJECT_STATUS.md、相關 docs/handoffs/ 紀錄，再核對實際檔案、近期提交與未提交修改。不要單憑聊天記憶重做已完成的功能。
- 實作以檔案與驗證為準；需求以最新明確指示為準；記錄衝突要指出，不臆測完成。歷史摘要中的測試與部署結果不適用於新版本。

### 每個任務自動留下紀錄
- 開始實作時建立獨立 `docs/handoffs/<日期>-<任務>-<唯一識別>.md`，記錄工作範圍、分支與涉及檔案；先查看其他 active 任務，避免重疊編輯。
- 在重要決策、可驗證階段完成，以及每次有實質進展的最終回覆前更新自己的紀錄，不需使用者另貼同步指令。
- 記錄含時區的更新時間、基準提交、目標、已實作/已驗證/未完成、取消的方案、驗證結果、下一步、commit/push 狀態。不可把中斷工作標成完成。
- PROJECT_STATUS.md 只放共同目標、穩定決策與交接目錄入口；詳細進度分散於各任務檔。修改共用文件前重讀，保留他人更新。
- 完成可交接工作時，檢查並只提交本任務相關且可分享的檔案，連同交接紀錄；沿用既有分支/PR 流程並推送已設定的遠端。若含其他任務未發布提交、未解決衝突或無法驗證內容，先回報，不能盲目全部加入。
- 不提交秘密、私人資料、原始聊天或無關修改；不 force push、不自動丟棄修改。雲端程式部署與 Git 同步不同，未另獲授權不執行部署。

### 自動化限制
- `.codex/hooks.json` 設定新建、恢復、分叉、壓縮後及每次新提示的同步檢查；需要本機 Codex 支援、Python 3、Git、遠端存取及專案/hook 信任。
- 新或變更的 hook 需要使用者在 Codex 的 hook 審查介面信任；CLI 可使用 `/hooks`。不得自行修改信任紀錄或繞過審查。
- 其他電腦必須先取得這些檔案並信任 hook。已開啟的聊天應重新讀取指引，不能假設即時載入。
- 檔案規則與同步鎖不是跨對話編輯鎖。多任務重疊時使用獨立分支/worktree，並明確整合。
<!-- END CODEX CROSS-SESSION SYNC -->


## 歷史專案導覽（使用前核對目前程式）

# Crypto Flash 專案記憶

最後核對：2026-10-07。這是依本機程式、測試與 workflow 整理的專案記憶；行為變更後應同步更新，實作與測試優先於可能過時的說明文件。

## 專案定位與技術

- 自架的加密貨幣／總體經濟新聞監控服務，主要介面為 Telegram；不是交易系統。功能包括即時快訊、新聞查詢、AI 問答、每日重點、事件追蹤、YouTube 摘要與經濟日曆。
- 目標與 CI 使用 Python 3.12；核心依賴是 `aiohttp`、`websockets`、`python-dotenv`，以 `asyncio` 執行。
- `src/` 是平面模組，使用裸模組名稱互相 import，沒有前端或資料庫。從 repository 根目錄執行入口。
- `common.py` 載入根目錄 `.env`、設定路徑／日誌／近期新聞保存；環境變數不少在 import 時讀取，測試須 patch 對應模組值。
- Telegram 01 處理快訊、查詢、問答、日報與日曆；02 處理 YouTube；聊天室由 `TELEGRAM_CHAT_ID` 設定。

## 入口與模組地圖

| 檔案 | 責任 |
| --- | --- |
| `src/flash_service.py` | 同程序啟動監控與 Telegram assistant，任一元件停止就取消其他元件並結束；標準入口為 `python src/flash_service.py` |
| `src/jin10_monitor.py` | Jin10 二進位 WebSocket 協定、去重、有界佇列、關鍵字過濾、Gemini 分級、保存與快訊推播 |
| `src/feed_monitor.py` | HTTPS RSS/Atom 正規化，來源在 `config/news_feeds.json`，預設每 120 秒輪詢並送入共用佇列 |
| `src/gemini.py`、`src/gemini_policy.py` | 模型呼叫、結構化輸出／搜尋引用，以及持久化請求預算、冷卻與錯誤分類 |
| `src/tg.py` | Telegram 發送、節流、重試、HTML 失敗處理與聊天室檢查 |
| `src/telegram_assistant.py` | Telegram long polling、聊天室限制、指令路由與含新聞背景的問答 |
| `src/news_commands.py` | `/news`、`/search`、`/important`、`/status`，以及非同步 `/digest` 路由 |
| `src/news_archive.py`、`src/daily_digest.py` | 歷史保存與「30 秒掌握大事」AI 彙整 |
| `src/event_tracking.py` | `/track`、`/tracks`、`/timeline`、`/updates`、`/untrack` 與已讀進度 |
| `src/yt_monitor.py` | YouTube 發現、摘要、Google Search 查證、分段送達與跨輪次接續，設定在 `config/yt_channels.json` |
| `src/economic_calendar.py` | Forex Factory 週 JSON 中的兩天 CPI／非農／FOMC 通知，不呼叫 Gemini |
| `src/monitoring_metrics.py` | 以台灣日期保存收件、過濾、去重、推播、失敗、佇列與延遲指標，預設保留 35 天 |

## 必須保留的行為

- 快訊先入有界佇列，再由 worker 比對關鍵字與呼叫 AI。佇列預設 200 筆，滿時丟棄最舊待處理項目，不阻塞接收端；這不是持久化發送佇列。
- `MEDIUM`、`LOW` 在分級後直接丟棄，不保存也不推播。`CRITICAL`、`HIGH` 先保存，再判斷相關性與推播門檻；有紀錄不等於已送達。
- Gemini 不可用時保留命中關鍵字的未分級背景，但不改發原文。背景恢復後不補發已略過快訊。不得把失敗摘要包裝成成功分析。
- RSS 與 YouTube 新來源首次抓取只建立已讀基準，不回播歷史。Jin10 去重為記憶體快取，RSS 去重狀態持久化。
- 近期新聞預設 6 小時／80 筆；歷史 archive 為 72 小時／5,000 筆。日期使用 UTC+8，新聞日報依收錄時間，不是來源發布時間。
- `/important` 顯示保存的 AI 摘要；`/news`、`/search` 是來源摘錄。`/status` 代表資料新鮮度，不代表連線健康。
- `/ask` 使用保存的資料，不即時搜尋網路。一般問題讀近期資料；含「今天／今日／本日／today」會讀台灣當天 archive；預設最多帶入 40 筆並優先匹配問題詞。
- `/digest` 與排程日報共用 AI 彙整：僅採相關且已有摘要的 HIGH／CRITICAL，合併同題，最多三點，正文上限 250 字，檢查 JSON、來源 ID 與長度。AI 失敗明確回報，不回退長篇原文；無合格資料則不呼叫 AI。互動查詢無摘要快取。
- 事件追蹤是大小寫不敏感的完整詞組比對，不做語意訂閱。聊天室共用最多 12 個主題，每個最多 40 字元；`/updates` 每次最多 8 筆，Telegram 成功後才更新實際顯示的進度。
- YouTube 先發現並保存所有頻道新片，再輪流處理，預設本輪工作預算 1,260 秒。單頻道上限限制嘗試次數，不代表可丟棄超額新片。
- YouTube 摘要失敗不推播、不標已讀；摘要成功但查證失敗可先送摘要，後續只補查證。已完成步驟與逐段發送進度須保留，待處理項目可離開 RSS 後繼續重試。
- 發送與本機／GitHub 狀態保存不是交易；Telegram 已收件但進度未落盤時仍可能重複，不能宣稱 exactly-once。
- Gemini 預算分 `live=600`、`youtube=120`、`digest=10` 次／台灣日，請求前先記帳，失敗也算。`0` 暫停、`-1` 取消本地次數上限；不是 token 或費用上限。
- 配額狀態讀寫失敗停止 API 請求。暫時錯誤保存退避時間；金鑰／設定錯誤封鎖自動重試；`GEMINI_POLICY_REVISION` 可使修復後設定重新評估，不能用來清除當日已用次數。

## 排程與狀態所有權

GitHub Actions 透過 `.github/actions/persist-state/action.yml` 將指定 JSON commit 回目前分支；衝突重試依賴每個狀態檔只有一個 writing workflow。新增流程不可隨意共寫同一狀態檔。

| Workflow | 時間／執行方式 | 負責的 `data/` 檔案 |
| --- | --- | --- |
| `flash_monitor.yml` | 每 6 小時，跑 `flash_service.py` 350 分鐘，job 上限 360 分鐘 | `recent_news.json`、`news_archive.json`、`event_tracking.json`、`gemini_live_usage.json`、`feed_seen.json`、`monitoring_daily.json`、`delivered_flashes.json`、`event_briefing_state.json` |
| `yt_monitor.yml` | 每 30 分鐘，外層執行上限 24 分鐘 | `yt_seen_ids.json`、`yt_progress.json`、`yt_schedule.json`、`gemini_youtube_usage.json` |
| `daily_digest.yml` | 台灣 08:15，整理昨日；獨立 digest 配額 | `daily_digest_state.json`、`gemini_digest_usage.json` |
| `economic_calendar.yml` | 台灣 08:00，今天至明天兩個日曆日 | `economic_calendar_state.json` |

- 監控與問答在同一 runner 共用即時檔案；獨立日報只讀 checkout 時已提交資料。排程有啟動延遲與重啟空窗，不保證無縫 24/7。
- `event_briefing.py` 在常駐服務每分鐘檢查事件前一小時窗口，同時事件合併，公布後不補發；使用台灣當天成功推播紀錄，正文 1,200–1,800 字，四段送達進度持久化，失敗五分鐘後重試並共用 live 配額。`delivered_flashes.py` 僅記錄 Telegram 回報成功的快訊，保留 72 小時，部署前舊 archive 不視為已送達。
- 經濟日曆只包含指定的美國 CPI、非農、FOMC 決議／預測／記者會；不含會議紀錄、談話或幣圈原生事件。抓取失敗以 30、120 秒間隔重試；全失敗通知後不推進寄送日期。
- `data/` 有刻意追蹤的營運狀態，不是可隨手清除的測試輸出；開發測試使用暫存路徑，記憶中不複製新聞原文、金鑰或聊天室識別碼。

## 開發與驗證

- 先讀 `CONTRIBUTING.md`；行為變更同步繁體中文與英文文件，並測試 parser、重試、狀態轉移與訊息格式等相關路徑。
- 安裝開發依賴：`python -m pip install -r requirements-dev.txt`。
- 檢查：`python -m ruff check .`、`python -m pytest`。Ruff 只啟用 E4/E7/E9/F 正確性規則，勿順便全專案重排格式。
- `pyproject.toml` 設定 `testpaths=["tests"]` 與 `pythonpath=["src"]`；`src/test_*.py` 是會接觸外部服務的診斷腳本，不是離線單元測試。
- 測試應無網路、無真實憑證；`tests/conftest.py` 隔離 Gemini 配額、YouTube 進度與指標，固定 Telegram 測試值並取消真實節流等待。
- `python src/feed_monitor.py` 是連網檢查來源；`python src/economic_calendar.py --dry-run` 連網預覽，不發送。直接執行日報／監控入口可能實際推播，不拿來代替離線測試。
- 2026-10-07 本機驗證限制：可用 Python 為 3.13.5，啟動時有 Python 路徑警告，且未安裝 Ruff。pytest 改用已建立的 workspace `.tmp/` 作為暫存父目錄後通過前 19 項，但後續長時間未進展而中止；未確認完整測試通過，也未判定為程式缺陷。此環境紀錄不是 CI 結果，後續應重新驗證。

## 已知文件落差

- `docs/README.md` 尚有 `/digest` 不增加模型呼叫、最多八則等舊敘述；現況以 `daily_digest.py`、`news_commands.py`、`docs/daily-digest.md` 與相關測試為準。
- 舊文件部分段落仍描述獨立 Telegram assistant workflow；現有 workflows 沒有該檔案，實際由 `flash_monitor.yml` 啟動合併服務。不要額外啟動第二個 polling consumer。
- README 圖示中的步驟次序是概述；實際關鍵字過濾在佇列 worker。YouTube 走自己的可接續處理流程，並非共用快訊分類佇列。

- 2026-10-14 驗證：事件提醒／分析及相鄰路徑 81 項離線測試通過。沙箱內 asyncio 最小程式也會停滯，沙箱外正常；完整測試兩次各有 3／2 項 YouTube 狀態檔替換遭遇 Windows WinError 5，失敗項目不同，未確認全套通過。Ruff 未預裝，安裝下載未完成，尚未完成 Ruff 檢查。

- 2026-10-14 部署驗證：已整合遠端主分支更新；新狀態檔遵循 CRYPTOFLASH_STATE_DIR。Ruff 檢查通過；GitHub CI 在 771dcf4 與 3a26101 均成功。economic_calendar 支援手動 force=true／--force 重送，一般排程仍依日期去重。

- 事件前分析手動預覽：flash_monitor 的 briefing_preview=true 建立兩天有效請求；只在請求後有當天新成功推播且有真實未公布事件時執行，訊息標示手動預覽，進度仍由 live workflow 保存。preview 請求與正常事件鍵分離，四段全部送達才完成；部署 8db1b18 的 CI 通過。

- 2026-10-15 快訊品質：提示詞將無實質新資訊的官員發言預告限制為最高 MEDIUM；自然繁體中文，僅有具體依據才加「市場影響」，保留推論條件、不補造數據。輸出整理空白與常見金融詞彙、移除空影響段落，Jin10 亦顯示來源。
