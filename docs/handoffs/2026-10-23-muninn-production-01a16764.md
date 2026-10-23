# Munnin production 啟用

更新：2026-10-23（Asia/Taipei）；基準 main / 785bc33，hook 已確認同步。
使用者明確要求 deploy to production。正式執行平台為 GitHub Actions yt_monitor.yml，從 main checkout；排程設定每 30 分鐘，實際可能延遲。
已確認新版程式提交 c0cc512 的 GitHub CI #70 通過：https://github.com/Yili-code/Crypto-Flash/actions/runs/39915573315 。其後 785bc33 僅交接紀錄，未改程式。
GitHub connector 無 workflow dispatch 功能，本機無 gh；改用既有登入 Chrome 的正式 GitHub UI，於 main 啟動 Run workflow。
正式 run #305：https://github.com/Yili-code/Crypto-Flash/actions/runs/39915946380 ，2026-10-23 15:09（Asia/Taipei）手動啟動 main。Checkout 日誌確認 785bc33c205a8805699ef22cbf1f2c53421e1c0b；含新版程式 c0cc512。
結果：Success，job 16 秒（含 runner 排隊總計 1 分 21 秒），Run YouTube monitor agent 及 Persist seen video ids 步驟均成功。
限制：Gemini youtube 請求收到 HTTP 429 rate_limit，後續請求 deferred: cooldown，待處理摘要及查證保留重試；加密龐克 RSS 回傳 404。不可宣稱本輪新生成摘要成功或新正式訊息送達。前次群組預覽送達證據是獨立本機驗證。
截圖：gitignored .tmp/muninn-production-success.jpg。
後續：既有排程從 main 執行並於冷卻後重試；RSS 404 與供應商 rate limit 為營運待查事項，不改配額或來源設定。本次不改其他服務、不提交本機配額或覆蓋正式狀態。交接紀錄提交推送結果以最終回覆為準。
