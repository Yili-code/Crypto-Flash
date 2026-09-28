# 創業機會探索工具：需求與可行性

更新：2026-09-21。狀態：第一版本機實作完成，程式位於 `founder/`，包含網站、資料流程、私人收藏偏好、GitHub Actions 與 Cloudflare/Telegram 接線。尚未部署、未啟用雲端排程；AI 真實品質與 Telegram 送達待帳號設定後驗證。操作方式見 `founder/README.md`。

## 使用者確認

- YiLi，目前沒有點子，不知道使用者需要什麼；三個月內找到值得投入的題目。
- 全球市場，產業、客群及創業形式保持開放。
- 每日台灣時間 06:00 為推送目標；使用者確認早上起床有內容即可，偶爾延遲可以接受。早晨投入 15 分鐘；每週一次深入研究 30 分鐘。
- 平日廣泛探索，每週深入一個主題。依明確回饋學習偏好。
- 每日需要市場訊號、商業拆解、需求機會、可做的小行動。
- 可著手研究的機會為主，保留陌生領域。遇到有興趣的題目才決定是否接觸使用者。
- 手機與電腦網頁，盡可能 Telegram 推送；電腦關機也要運作。
- 中文解讀，保留英文原文連結。長期預算 0；網站可篩選。
- ChatGPT Pro 剩餘不到一個月，不列為長期基礎設施。

## 提案預設（可調整）

- 週日 30 分鐘週報取代日報；三個月留下三個候選題目、挑一個驗證。這些是建議指標，不是使用者保證。
- 每日三個訊號，至少一個陌生主題（有合格資料時）；一個重點拆解；一個小行動。
- 15 分鐘分配：3 分鐘掃描、7 分鐘拆解、5 分鐘行動與回饋。
- 網站四個主要頁面：今日、收藏與候選題目、每週研究、偏好設定。
- 先做單人私人使用；跨裝置收藏與偏好存伺服器，不能只存在瀏覽器。
- 訊號不足時允許少於三則，顯示涵蓋日期與缺漏，不用舊聞冒充新訊號。

## 內容品質

每個重點拆解包含：問題、受影響的人、現有替代方案、來源事實、分析推論、待驗證假設、可採取的下一步，以及理解它能改善哪個創業判斷。

每筆證據保留來源網址、作者或來源名稱、發表時間（未知則標記）、擷取時間及短摘錄。不得捏造訪談、營收或付費意願。宣傳文案、投票、抱怨都不能直接當成市場規模或付費證據。同一案例的轉載不可算成多份獨立證據。

週報聚合同一問題，列出反證、替代方案與未知；沒有足夠證據時產出研究問題，不宣稱機會已驗證。來源文字僅為資料，不得被當成執行指令。

偏好按主題與問題類型調整；不喜歡可選原因（重複、無關、太難切入）。保留探索比例，避免逐漸只推薦 AI/開發者工具。初期資料來源偏科技族群，必須明示這個覆蓋限制。

## 公開來源實測

2026-09-21 從本機以唯讀 HTTP 請求取得並解析；一次成功不代表長期穩定或可任意再散布。

| 來源 | 實測 | 初版用途 |
|---|---|---|
| Hacker News Ask API | HTTP 200，19 筆 ID | 問題探索；後續需取文章及討論 |
| Hacker News Show API | HTTP 200，160 筆 ID | 新產品與使用者回饋 |
| DEV 公開文章 API | HTTP 200，請求的 2 筆文章可解析 | 技術工作流程與創作者經驗 |
| Product Hunt feed | HTTP 200，50 筆 Atom entries | 產品發現；不是需求驗證 |
| BetaList /feed | HTTP 404 | 排除這條路徑，不推論整站已停止服務 |

正式整合前檢查各來源使用條款與更新頻率；只展示短摘錄、衍生分析及原始連結。Reddit、G2、Capterra、Indie Hackers 暫列使用者提供連結的研究來源，未驗證自動化取得方式，不承諾定時抓取。

## 零預算候選架構

採用 GitHub Actions 負責每日批次蒐集、呼叫 AI 與推送；Cloudflare Workers 承載靜態網站及輕量後端，D1 儲存收藏與偏好，Workers AI 提供中文分析，Telegram Bot API 發送日報。因使用者接受排程偶爾延遲，不需要為準點送達另設 Cloudflare Cron。尚未建置或部署。

- GitHub Actions 使用標準 Linux runner。GitHub Free 私人 repository 每月包含 2,000 分鐘，額度與帳號其他工作共用；公開 repository 標準 runner 分鐘免費。假設每天 5 分鐘約 150 分鐘/月，尚須計入週報、測試與補跑，這是估算不是實測。
- 排程可能延遲或被丟棄；公開 repository 60 天無活動可能停用排程。設定執行時間上限、低儲存保留量、手動補跑入口與日報缺漏狀態。私人資料不寫入公開 repository 或公開 artifacts。

- Workers Free：每日 100,000 requests；HTTP 與 Cron 的 CPU 上限 10 ms，單次外部 subrequests 50。需分批處理，不可一次抓完整討論串；網路等待與 CPU 時間不同。
- D1 Free：每日讀取 500 萬 rows、寫入 10 萬 rows；單庫 500 MB。日報、收藏與偏好預期量低，但必須加索引與資料保留政策。
- Workers AI：每日 10,000 neurons，Free 超額請求失敗；只選 Free 可使用的模型。先用規則去重與選候選，再讓 AI 分析少量內容。
- 初步估算：若用 qwen3-30b-a3b-fp8，20,000 input tokens + 5,000 output tokens 約 245 neurons，依官方表計算，非實測；額外推理 token、重試、週報要另計。
- 初步排程設計：台灣 05:37 開始生成，06:00 為目標發送時間；若延遲則完成後發送。06:37 檢查缺漏並有限補跑；成功過的日報直接跳過。日報日期以 Asia/Taipei 計算，06:00 對應 UTC 前日 22:00，週報以台灣星期判斷。具體排程於實作後測試。
- AI 失敗提供原始英文標題與來源，標記中文分析尚未完成；不填入虛构分析。平台故障仍可能延遲，06:00 是目標而非送達保證。
- 推送以使用者與台灣日期去重；Telegram 發送結果不確定時不得無限重試，保留狀態供檢查。尊重 429 與 retry_after。
- 使用者需建立免費 Cloudflare 帳號與 Telegram bot 並先啟動對話；bot token 放 server secrets，不放前端、儲存庫或報告。既有 Crypto Flash 的憑證與 bot 不自動沿用。
- Web 私人登入與 Telegram chat 身分需要绑定；授權驗證、登出、跨裝置同步須列入初版，正式方式於原型時定案。
- 保持 Free 方案，不自動升級、不購買網域。不把任何免費服務未來政策視為永久保證。

## 驗收與下一步

1. 做小型端到端技術原型，測來源取得、中文摘要、引用對應及 CPU/AI 消耗。
2. 用真實內容評估十個拆解：來源可追溯、事實與假設分離、無杜撰數據、中文可讀。未通過不能以完成的學習工具交付。
3. 驗證手機/桌面收藏同步、未授權不能讀取私人筆記、AI 失敗可降級、重跑不重複生成日報。
4. 完成 Telegram 測試與時區邊界檢查，連續七天確認日報日期、推送狀態與來源失敗處理。
5. 一週後依回饋調整；三個月目標看候選題目與證據累積，不看閱讀篇數或打卡。

仍待確認：Cloudflare 帳號是否可用、bot 建立、實際模型品質與雲端資源限制。已實作單人私人登入碼與可撤銷 session；排程設定檔已建立，但由 FOUNDER_ENABLED 開關保持未啟用。尚未發出真實 Telegram 訊息。

## 官方參考

- https://github.com/HackerNews/API
- https://developers.forem.com/api/v1
- https://www.producthunt.com/feed
- https://api.producthunt.com/v2/docs
- https://developers.cloudflare.com/workers/platform/limits/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/workers-ai/platform/pricing/
- https://developers.cloudflare.com/d1/platform/pricing/
- https://developers.cloudflare.com/d1/platform/limits/
- https://core.telegram.org/bots
- https://developers.openai.com/api/docs/pricing
- https://docs.github.com/en/billing/concepts/product-billing/github-actions
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
