# Live functionality verification

更新：2026-10-26 19:33（Asia/Taipei）；基準 f0bba80；分支 main。
授權：使用者要求檢查現有服務功能。已讀 PROJECT_STATUS、部署 handoff 與實際健康檢查/授權程式；hook ahead=0/behind=0。
驗證方式：computer-use 檢視已開啟 Unigram 的既有 Crypto flash 群組，使用正式 @heimdall_notify_bot 進行唯讀指令 smoke checks，無 getUpdates 競爭、無本機 bot 代測。
已驗證：
- GitHub run 40315171202/job 121545842449 monitor/assistant step 仍 in_progress，dependencies success。
- /news@heimdall_notify_bot 19:31 送出並收到近期快訊回覆，中文介面為繁體，英文來源保留英文。
- 既有使用者 /important 19:28 回覆可見，中文摘要為繁體；不把此項聲稱為 agent 新送出的測試。
- 輸入 / 實際出現 news/important/digest/tracks/updates/status/help 七項；點選 status 即送出並收到正常回覆。
- /health 19:31 收到 Critical 0 / Warning 2；YouTube pending 161、Flash classification pending 0。Warning 為 161 影片待完成與 owner allowlist 未設定。這是 persisted health，不能證明所有外部 provider uptime。
- /tracks 19:33 收到正常追蹤清單，有既存主題與未讀數，未讀取 updates 或變更追蹤狀態。
風險：sender_is_authorized 在 OWNER_USER_IDS 為空時直接允許，因此目前 owner-only commands 對設定聊天室成員無 owner ID 限制；未擅自修改 security settings。
限制：本輪沒有重跑已成功的 352 項離線測試；既有 CI 40314888616 為通過證據。沒有以正式 /digest 或 /ask 新增模型請求，未實測本輪 YouTube 送達、外部資料源全貌或事件提醒時點。沒有新增/刪除追蹤或改未讀進度。繁體轉換的簡體來源/數值/URL 保護由先前九項新增測試涵蓋，當前 /news 為英文來源，不能當成簡轉繁實際例子。
結論：群組 menu、指令路由、查詢/追蹤清單回覆已 live 確認；存在兩項健康警告，不能宣稱全部功能健康。
commit/push：僅提交本查核紀錄，無程式修改或重新部署。
