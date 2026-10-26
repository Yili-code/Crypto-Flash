# Concise reply production rollout

更新：2026-10-26（Asia/Taipei）；基準b0342a4；分支main。
授權：使用者明確要求部署精簡回覆。
已核對hook ahead0/behind0、PROJECT_STATUS、精簡handoff、實際diff/狀態；tracked乾淨。
驗證基準：8c63739，375項測試/Ruff通過，CI40323041858成功。
操作：取消舊active run40318803031及pending40321336677，避免舊版本等待後接手；新版dispatch至同一jin10-monitor concurrency（cancel-in-progress=false），保證舊run結束才接手，checkout ref=main讀最新狀態。
模型：主模型與搜尋均維持已授權3.5 Flash-Lite；不開billing。
已確認：舊run completed/cancelled，health與persist-state均success，狀態提交c5fead2已快轉至本機。新版run40330088907/job121597674155，head=c5fead2，git ancestor確認包含受測修正8c63739；dependencies success，live monitor/assistant in_progress。
已實測：Unigram正式群組 /news 正常，保留標題/時間/來源/短摘錄，無筆數/UTC/tiers；/health為繁中簡短標題及兩條實際警告，無零計數/重複英文診斷。使用者輸入偵測後重新觀察/確認空白輸入框才續行，未覆寫草稿。
已實測：21:29 /ask 收到一段式簡短回覆與來源，不再四個強制標題；21:30 /digest today 正常生成，無30秒宣傳/UTC/未分級筆數，只有確實有未納入消息時的短提醒；/tracks正常，保留原主題與未讀筆數，只附一行可用操作。無更動追蹤進度。
部署網址：https://github.com/Yili-code/Crypto-Flash/actions/runs/40330088907
限制：既有YouTube Google Search免費tier限制仍未解決，本部署僅訊息精簡，不宣稱影片查證已恢復。/health實際顯示影片與新聞待處理警告，未隱藏問題。未重跑受測且未改動的375項測試，沿用8c63739與CI40323041858。
commit/push：僅提交本部署驗證紀錄；無額外程式修改。
