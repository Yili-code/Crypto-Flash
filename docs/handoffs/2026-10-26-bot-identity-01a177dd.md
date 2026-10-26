# Production bot identity mismatch

更新：2026-10-26 19:20（Asia/Taipei）
分支：main；基準 ad02613；hook ahead=0/behind=0。已讀 PROJECT_STATUS、restart handoff、assistant 與 tg 實作。
問題：重啟後使用者送出指令仍無回應。
已查：run 40313927380/job 121541658252 live monitor step 仍 in_progress。執行中 job logs API 回 BlobNotFound，不能聲稱已讀到該輪 listener 日誌。
關鍵證據：前一輪 production run 40263391089/job 121395931905 的日誌：2026-10-26T04:19:37.8209272Z Telegram Assistant listener started. Bot username: @heimdall_notify_bot。
本機 getMe 為 @jin10_my_alert_bot；本機 .env 與 GitHub 正式 secrets 指向不同 bot。先前以本機 getMe 給使用者 /news@jin10_my_alert_bot 是錯誤定位；手動 default/chat menu 更新亦是針對本機 bot，不可宣稱正式 bot 的群組選單已手動更新。
已實作的 startup sync 使用正式 runner 的 token，因此會對該 runner 的 bot 註冊預設 menu；尚無 client 或本輪 getMe 證據確認顯示。
下一步：使用者以 /news@heimdall_notify_bot 驗證。若仍失敗，取得本輪實際 listener 日誌或核對群組內 bot 身分與 production chat restriction。不要呼叫 getUpdates 競爭既有 consumer，不把本機設定視為 production。
未修改 production secrets、未再重啟，無應用程式變更。未還原另一 bot 的 menu，缺少修改前完整 scope 快照。
commit/push：僅提交本診斷紀錄。
