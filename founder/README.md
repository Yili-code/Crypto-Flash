# 拾題 · Founder Morning

YiLi 的個人創業研究工具。每日 15 分鐘，週日 30 分鐘：公開來源 → 偏好篩選 → 中文拆解 → 網站與 Telegram。與 Crypto Flash 的服務、憑證、資料及排程分開。

## 已實作

- HN Ask/Show、Product Hunt Atom、DEV 公開 API；單一來源失敗可降級。
- 近七天候選、已讀期別去重、明確偏好排序、保留陌生主題。
- 中文分析區分來源描述、推論、收費假設、未知、反證與具體行動；AI 格式或引用 ID 不合格時只顯示原文。
- 私人登入、30 天 HttpOnly session、登出撤銷、登入限流、跨站寫入阻擋；SQLite/D1 同步收藏、反應與筆記。
- 今日、候選題目、每週研究、探索偏好；手機與桌面版。
- GitHub Actions 預備、發送、補跑；D1 日期鎖避免重複發送；網路結果不確定不自動重送。

## 本機體驗（不需安裝 npm 套件）

需要 Node 24、Python 3.12+。在 repository 根目錄執行：

```powershell
python founder/pipeline.py --local-output founder/.local/issue.json
node founder/local.mjs
```

開啟 http://127.0.0.1:8787，登入碼 `morning-local`。可用 `FOUNDER_APP_KEY` 覆寫本機碼。預覽僅綁定 127.0.0.1，資料存在已忽略的 `founder/.local/state.sqlite3`。不連接 Telegram、不使用既有 `.env`。無 AI 帳號時真實來源可用，但中文拆解顯示尚未完成。

## 一次性 Cloudflare 設定

建立免費帳號後，在 `founder` 目錄操作。需要可用的 Node/npm 與 Wrangler CLI；保持 Workers Free，不升級計費。

```text
npx wrangler login
npx wrangler d1 create founder-morning
```

複製 `wrangler.example.toml` 為 `wrangler.toml`，填上回傳的 database_id，設定 SITE_URL。不要提交本機憑證或 `.dev.vars`。

```text
npx wrangler d1 migrations apply founder-morning --remote
npx wrangler secret put APP_KEY
npx wrangler secret put JOB_TOKEN
npx wrangler secret put TELEGRAM_BOT_TOKEN
npx wrangler secret put TELEGRAM_CHAT_ID
npx wrangler deploy
```

APP_KEY 與 JOB_TOKEN 各使用不同的隨機 32 bytes 以上值（例如密碼管理器產生），不要用本機範例碼。APP_KEY 為網站私人登入碼；JOB_TOKEN 僅用於 GitHub Actions。兩者不要放在公開網址或前端程式碼。若要撤銷所有 session，可在 D1 執行 `DELETE FROM sessions`。

Telegram：向官方 @BotFather 建立自己的 bot，私訊 bot `/start`；將 bot token 與你自己的 chat ID 填入以上 secrets。不要沿用 Crypto Flash 的 bot，除非你明確決定要共用。網站收藏與 Telegram 的設定 chat 屬於同一個單人帳戶；本版不是多使用者系統，不開放其他人登入。

## GitHub Actions 啟用

將程式碼推到 repository 的 default branch，設定：

| 類型 | 名稱 | 值 |
|---|---|---|
| Repository variable | FOUNDER_URL | 部署的 HTTPS 網站網址 |
| Repository secret | FOUNDER_JOB_TOKEN | 與 Worker JOB_TOKEN 相同 |
| Repository variable | FOUNDER_ENABLED | `true` 才啟用，未設定時不執行 |

在 Actions → Founder Morning 手動執行一次，會準備日報並傳送 Telegram。這是真實發送操作，確認 chat ID 指向自己後再執行。

排程為台灣 05:37 準備，06:07 發送，06:37 補跑。避開整點尖峰；GitHub 可能延遲。重跑使用同一天的既有日報，只檢查推送狀態。公開 repository 無活動 60 天可能停用排程，應定期確認。私人 repository 使用額度與其他專案共用。設定 GitHub 消費上限與短期儲存保留；本 workflow 不上傳 artifacts 或寫入私人資料到 repository。

## 驗證

```text
node --test founder/tests/worker.test.mjs
python -m unittest discover -s founder/tests -p "test_*.py"
```

自動驗證涵蓋未授權存取、session 隔離與撤銷、限流、跨裝置持久化、來源去重、偏好探索、引用 ID 驗證、日期邊界、推送去重與不確定失敗。正式上線仍需真人檢查十個中文拆解與七天排程紀錄。

## 邊界

- 初期來源偏科技族群。週報按主題聚合，不代表不同產品已證明同一個需求。
- AI 引用 ID 驗證只確認引用存在，不能保證每句推論成立；必須讀原文。
- Workers AI 限制應用每天最多六次分析呼叫；模型仍受平台免費額度限制。
- 本機不用 AI binding；正式 AI 品質、Cloudflare Free CPU 消耗與 Telegram 送達需要帳號設定後驗證。
- Telegram `unknown` 或停留在 `sending` 代表可能已送達，先確認對話再人工處理 deliveries 紀錄；不能保證外部服務 exactly-once。
- 網站及 API 是單人私人使用。公開頁面只有登入外殼，私人內容與偏好由 session 保護；job token 可管理研究資料，務必保密。
- 尚無自動資料清理；以個人三個月試用為初版範圍，長期運行前檢查 D1 容量。
