# Full functionality validation

更新：2026-10-26 19:43（Asia/Taipei）；分支 main；起始基準 809dc66，查核營運提交後為 4a7ea96。
授權：使用者要求完成剩餘功能測試；已讀 PROJECT_STATUS、前次 live check、實際指令、狀態與 workflow。hook 起始 ahead=0/behind=0；本輪 YT workflow 保存狀態後 git fetch/ff 取得最新提交。
範圍：正式 Telegram 全部 commands、AI、追蹤生命週期、YouTube、排程日報、日曆、事件提醒與新聞來源。

## 實際 Telegram 測試
使用 computer-use 操作既有 Unigram 群組、正式 @heimdall_notify_bot；無 getUpdates 競爭，無本機 token 代測。
- 前輪已 live 確認 menu 七項、news、status、tracks、health；本輪繼續全部其餘指令。
- 19:35 /ask：真實 Gemini 回覆送達、繁體中文，回答依據保存的最新新聞。
- 19:35 /digest today：真實 AI 日報送達；19:38 /digest：昨日日期正確，正常送達。
- 今日摘要主要量化與事件敘述核對本機同步 archive：8 筆合格保存來源；90% 利率預期、BTC 曾低於八萬與之後接近八萬、伊朗相關敘述均有來源依據。不是外部事實的獨立重新查證。
- 19:36 /search Bitcoin：找到現有新聞。
- 19:36 /track CFValidation1936：成功建立獨立測試主題。
- 19:37 /updates CFValidation1936：正確回覆無新進展，未消耗既有主題未讀。
- 19:37 /timeline Bitcoin：三筆事件依時間顯示，中文由原始/保存內容正常轉繁體。
- 19:37 /untrack CFValidation1936：成功移除；19:41 /tracks 確認只保留原主題與原未讀數。
- 19:38 /help、19:41 /start：均導向繁體分類說明。
- 19:41 /important：本輪親自送出並取得繁體摘要。

## 外部與排程測試
- 新聞 5 個 RSS：CoinDesk 25、Decrypt 40、SEC 25、CFTC 10、Federal Reserve 20 筆，全部抓取/解析成功。唯讀 check_feeds，不改 seen。
- Jin10：新建獨立來源連線（非 Telegram consumer），WebSocket 握手/login 成功，解析 4002 dict 與 1200 list，沒有投入正式 queue、未發送歷史資料。
- YouTube RSS：6 個中 5 個 HTTP 200，Bankless HTTP 404；不再把較早整輪六個 404 當成目前狀態。
- 手動正式 YT run 40316682228/job 121550927063 已 completed/success，但日誌確認 Bankless 404 與 Gemini youtube HTTP 429、後續 cooldown。未完成摘要/查證保留，persist seen/progress/schedule/quota step 成功。此項功能測試判定未通過，不將 job success 說成成功送達。同步後 quota state last_error=rate_limit、blocked=false，不能宣稱永久封鎖或當日配額耗盡。
- 日報正式 run 40316687260/job 121550943480：已送昨日，正確去重略過；本輪 UI default/today digest 已獨立驗證真實生成與送達。
- 日曆正式 run 40316691476/job 121550957558：force=false，已送日期去重，沒有狀態變更；最新來源 fetch/select/render 成功。此前日曆 job 121374624068 有 Calendar notification delivered for 2026-10-26 日誌。
- 事件前分析：目前 fetch/select events=0、due=0，正確情境為不發送；不捏造事件或強制假提醒。

## 模擬與失敗路徑測試
本輪擴大驗證新增執行 193 項測試，全部通過（4.38 秒）：daily_digest、event_briefing、economic_calendar、yt_monitor/progress/research/scheduler、event_tracking、chinese_output、telegram。
涵蓋正負例、AI 回應驗證、事件前窗口/公布後停止、四段續傳、發送失敗不推進狀態、YouTube 摘要/查證分開恢復、去重、追蹤正進展 acknowledgement、繁體/HTML/URL 保留。
先前全套 352 項與 CI 40314888616 已通過；不把本輪 193 加總成不同測試數。

## 結論與後續
本次計畫中的指令、來源、正式流程與模擬失敗路徑都已執行，結果不是全部通過。
失敗/風險：YouTube 受 HTTP 429 與 Bankless RSS 404 阻擋完整送達；owner allowlist 未設定，群組成員均可用 owner-only commands（實作確認）。不改動 secrets、權限或 retry policy 以掩蓋問題。
事件時點與新片完整送達的正例不能透過製造假事件/略過失敗替代；已完成當前實際條件的測試並記錄外部阻擋。
測試主題已清除，既有主題未讀保留。無應用程式修改、無重新部署常駐服務。
commit/push：僅提交本驗證紀錄。
