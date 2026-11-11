# 快訊推播量診斷

更新：2026-11-11 22:49 Asia/Taipei。範圍：唯讀診斷與方案。main 本機 9bbf769，與已抓取 origin/main 23ba36e 相差 108 個提交，保留原有兩份未追蹤交接。已讀專案索引、既有快訊品質與 10/30 workflow 交接，以及上游實作和狀態。

- 10/26–30、11/2–6 同為工作日，成功推播 124→38，關鍵字命中 1287→1162，gemini_failures 54→167。11/7–8 推播 0、2，11/9–11 回升至 9、21、24（11/11 資料至 18:37 保存點）。11/5–11 無 CRITICAL 推播。11/5–11 已保存的 Telegram 失敗和接收佇列丟棄均為零。
- 5ab0de4 記錄 11/5 timeout；5689826 與 a646c1d 記錄 daily_quota，保留 retry_at 至 11/7 12:55 台灣時間。程式對 daily_quota 至少冷卻 24 小時，台灣換日只重設本地計數。gemini_failures 非唯一文章/API 失敗數，不含直接跳過的 unavailable 分支。
- Backlog 預設一小時有效；恢復時只取一次最多 25 筆，其餘無持續排空保證。23ba36e 保存的 backlog 為空，不能推定舊項目全部成功處理。未查證近期 Actions 逐次覆蓋、來源故障或分級召回率。
- 下一步建議先確認 Gemini 配額重置與隔離額度的備援，持續限速排空仍新鮮的 backlog，再補來源／分級／等待到期漏斗與抽樣回放。保留 HIGH/CRITICAL 門檻直到取得漏判證據。
- 本輪只有診斷交接，無程式變更、測試、commit、push 或部署。

## Implementation

Updated 2026-11-11 22:55 Asia/Taipei. Verified main and origin/main had converged at b2eb762 before editing. Preserved the separate daily-digest handoff edit and other untracked work.

- Gemini daily quota cooldown now uses the next Pacific midnight or a later provider hint. The Taiwan-day local budget and already stored deadlines retain their semantics.
- The flash recovery loop replays up to 25 fresh records per pass, newest first, then uses its existing reconnect interval before the next pass. A renewed classification failure pauses replay without renewing the failed record's freshness.
- Ruff passed. Full offline suite passed 389 tests using system temp storage, after a workspace-temp attempt hit three Windows file replacement errors. No production API or Telegram calls. Next step is the normal Git sync and CI path.
Direct main commit/push was rejected by automatic review. Verified the unrelated digest handoff is a separate file and excluded. Use a feature branch to keep the fix separate from main.
