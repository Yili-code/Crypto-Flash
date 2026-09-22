<div align="center">

# Crypto Flash

**快訊分級 · 新聞查詢 · 每日重點 · 事件追蹤**

這個專案會持續監控 Jin10 的 WebSocket 快訊，當新聞命中你的關鍵字時，會交給 Gemini 進行分級與摘要，並自動推播到 Telegram。你也可以直接在 Telegram 提問，系統會把近期已監控的快訊背景一併納入回答。

[![GitHub Actions](https://img.shields.io/badge/自動化-GitHub%20Actions-2088FF?logo=githubactions&logoColor=white)](.)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](.)
[![Gemini](https://img.shields.io/badge/AI-Gemini-8E75B2?logo=googlegemini&logoColor=white)](.)
[![Telegram](https://img.shields.io/badge/推播-Telegram-26A5E4?logo=telegram&logoColor=white)](.)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**[English](README.en.md) | 繁體中文**

</div>

<div align="center">
<table>
<tr>
<td align="center" width="33%">
<img src="../assets/demo001.jpg" width="100%"><br>
<sub><b>分級推播</b><br>Gemini 會依新聞重要性分級</sub>
</td>
<td align="center" width="33%">
<img src="../assets/demo002.jpg" width="100%"><br>
<sub><b>AI 即時回覆</b><br>帶入近期快訊背景補充判斷</sub>
</td>
</tr>
</table>
</div>

---

## 專案概述

這是一個以 GitHub Actions 為核心的自動化快訊監控系統，目標是把大量、低價值的 Jin10 訊息濾掉，只留下值得你關注的內容。

### 它做了什麼

- 直接連接 Jin10 的 WebSocket 訊號流
- 解析快訊內容並以關鍵字過濾雜訊
- 將符合條件的新聞交給 Gemini 做分級、摘要與風險判斷
- 把重要內容即時推到 Telegram
- 另外支援 Telegram 問答模式，帶入近期快訊背景回答
- 監控 YouTube 頻道 RSS，新影片交給 Gemini 依影片內容彈性整理摘要並查證關鍵論點後推播到 Telegram

---

## 主要功能

- WebSocket 連線與自動重連：`src/jin10_monitor.py`
- 關鍵字過濾：支援內建關鍵字清單，也可用 `KEYWORDS_FILE` 自訂
- Gemini 分級與摘要：`src/gemini.py`
- Telegram 推播：`src/tg.py`
- Telegram 對話問答：`src/telegram_assistant.py`
- YouTube 新影片監控與摘要：`src/yt_monitor.py`
- 新聞查詢與狀態：`src/news_commands.py`，支援 `/news`、`/search`、`/important`、`/status`
- 每日重點：`src/daily_digest.py`，支援 `/digest` 查詢與每日 08:15（UTC+8）推播
- 三天經濟日曆：獨立排程每日 08:00（台灣時間）通知美國 CPI（含核心）、非農就業、FOMC 決議／經濟預測／記者會，以台灣時間每行列出日期、時間與事件名稱；涵蓋今天、明天、後天；無符合事件時明確顯示日期範圍、篩選條件及「這三天沒有 CPI、非農或 FOMC」提示。

- 事件追蹤：`src/event_tracking.py`，支援主題訂閱、時間線與未讀進展
- 歷史新聞保存：`src/news_archive.py`，供日報與事件追蹤共用
- Gemini 故障後背景重試、Telegram 限流重試與有上限的快訊處理佇列
- 共享近期新聞上下文：`data/recent_news.json`
- GitHub Actions 自動執行：Jin10 每 6 小時一次，YouTube 每 30 分鐘一次，皆支援手動觸發

經濟日曆使用 Forex Factory 的公開每週 JSON，不呼叫 Gemini。以台灣今天 00:00 至大後天 00:00（不含）篩選，共三個日曆日，包含今日 08:00 前已發生事件。依事件名稱篩選，不依來源影響分級；排除 FOMC 會議紀錄、官員談話及其他數據。同時發布的 CPI 項目及 FOMC 利率／聲明合併顯示。可用 `python src/economic_calendar.py --dry-run` 讀取真實來源並預覽，不發送訊息。

排程檔為 `.github/workflows/economic_calendar.yml`，使用既有 Telegram secrets，合併／推送至 GitHub 預設分支才會啟用。GitHub Actions 可能延遲執行，無法保證準點送達。若抓取失敗、來源過期或跨週資料不足（三天範圍跨越來源週界時），會通知「資料暫時無法確認」，不會誤報沒有事件。空結果只代表來源中沒有符合 CPI、非農、FOMC 篩選的資料；不代表幣市沒有重大事件。目前未接入幣圈原生事件，未與官方日程交叉驗證，也沒有事件前倒數提醒。週界檢查不能證明來源事件完整。成功後獨立保存當日送達狀態；發送成功但狀態回存失敗時，重跑仍可能重複通知。

---

## 工作流程

### Gemini 用量與重試

- 每日以台灣時間 00:00 重置請求次數預算：YouTube 預設 120 次，快訊與問答（含連線檢查）共 600 次。網路請求前先記帳，失敗、取消與重試都計入；冷卻或預算用完時不發請求、不加計次數。這不是 token／金額上限，也不是 Google 帳戶的剩餘配額。
- 暫時性限流、逾時、連線、5xx 或無效回覆採約 30、60、120 秒逐步延長的等待時間（附少量隨機延遲，最高 1 小時）。`Retry-After` 或 `RetryInfo` 要求更久時遵守較長時間。明確的每日配額錯誤保守暫停至少 24 小時；Google 的 RPD 重置採 Pacific time，與本地預算不同。一般 429 不會一律等到隔天。
- 冷卻期限保存後立即返回，由快訊恢復迴圈或後續 YouTube 排程在期限後再試，成功後清除連續失敗次數。YouTube 未完成進度會保留。
- 金鑰／權限或模型／帳戶設定錯誤停止自動重試；無效請求只封鎖相同內容。修正金鑰／模型後自動解除；修正外部帳戶設定後可更改 `GEMINI_POLICY_REVISION` 解除封鎖與冷卻，當日已用次數仍保留。
- 使用 `.env` 或同名 GitHub Actions Variables 設定 `GEMINI_YOUTUBE_DAILY_REQUESTS`、`GEMINI_LIVE_DAILY_REQUESTS`：`0` 暫停、`-1` 關閉本地次數上限。預設兩個服務合計 720 次／日。
- 計數、錯誤類別與最早重試時間分別存在 `data/gemini_youtube_usage.json`、`data/gemini_live_usage.json`，各 workflow 只保存自己負責的檔案。檔案損壞或無法寫入時停止請求。這限於本專案配置的單一寫入程序／各 workflow，不涵蓋其他程式或電腦使用同一 API key 的用量。
- 強制終止或 GitHub 回存失敗可能遺失尚未提交的計數；回存失敗會明確標示 workflow 失敗。此機制不是帳單硬上限。

```text
Jin10 WebSocket → 解析封包 → 待處理佇列 → 關鍵字比對
   ↓
Gemini 可用：分級與摘要；不可用：保留未分級紀錄
   ↓
保存 recent_news.json（預設 6 小時 / 80 則）
保存 news_archive.json（72 小時 / 5,000 則）
   ↓
有摘要、相關且達推播門檻 → Telegram 即時推播

recent_news.json → 新聞查詢、狀態與 AI 問答背景
news_archive.json → 每日重點、事件時間線與追蹤進展
```

`flash_service.py` 在同一個 runner 同時執行監控和問答，即時共用 `recent_news.json`。舊版分開執行的 Telegram Assistant workflow 必須停止，避免重複接收 Telegram updates。

Gemini 啟動檢查或執行中的摘要請求失敗時，快訊監控會暫停推播並在背景每 30 秒重新檢查連線，成功後自動恢復摘要推播。中斷期間仍接收快訊並保存符合關鍵字的新聞背景，不會改推原文；這些已略過的新聞不會在恢復後補發。未設定 API key 時也會暫停推播。這項恢復機制與 Jin10 WebSocket 原有的斷線重連分開運作。

保存發生在推播門檻判斷與 Telegram 發送之前，因此「有紀錄」不等於「已推播」。預設 `MEDIUM` 門檻會推送 CRITICAL、HIGH、MEDIUM；LOW 分級快訊直接丟棄，不保存至近期紀錄或歷史資料，也不推播；未分級資料仍會保留。佇列滿時會丟棄最舊待處理項目，這些項目不會進入保存流程。

### YouTube 影片監控

`yt_monitor.py` 會讀取 `config/yt_channels.json` 中的頻道，透過 YouTube RSS 找出新影片，再依序執行以下流程：

```text
YouTube RSS
   ↓
依 channel_id 解析影片
   ↓
比對 data/yt_seen_ids.json 去重
   ↓
Gemini 觀看影片並依影片內容彈性整理摘要並查證關鍵論點
   ↓
Telegram 推播摘要與來源連結
```

首次執行某個頻道時，程式只會把 RSS 中現有影片寫入 `data/yt_seen_ids.json` 作為預熱，不會推播既有影片。之後抓到的新影片全部保存至待處理清單，`max_new_per_run` 只限制該頻道單次嘗試的影片數（包含重試），不會因超過上限而標記已讀或丟棄。即使 Gemini 摘要失敗，仍會推送影片連結。

每輪先抓取並保存所有頻道，再以每頻道一部的方式輪流處理，例如 A1 → B1 → C1 → A2 → B2 → C2。每次嘗試前將下一個頻道寫入 `data/yt_schedule.json`，中斷後接續；完整跑完也會輪換下次起始頻道。預設 21 分鐘停止本輪處理，剩餘影片留待後續排程。Telegram 暫時不可用時仍保存新片。此機制只能保留已抓到的影片，停機期間已離開 RSS、從未被抓到的影片無法自動補回；舊版曾因上限標記已讀的影片也不會自動回播。

摘要固定包含「一句話結論、主要論證、實際用途」，其餘結構與篇幅依每支影片調整；頻道提示僅設定內容側重。接著透過 Gemini Google Search 查證重要論點，附上 API 回傳的對應來源，並與影片原意分開呈現。搜尋失敗或沒有可引用來源時，保留摘要並標示「外部查證未完成」。這會增加 API 用量與處理時間，搜尋費用依 Google 帳戶方案計算。

每部新影片另外在 `data/yt_progress.json` 記錄「已通知、摘要完成、查證完成」，並保存產出的內容與送達進度。摘要失敗時先發一次影片連結；後續排程重試摘要。摘要完成但查證失敗時先發摘要並標示待查證，恢復後只補送查證結果。已完成步驟不會重做；待處理影片即使離開 RSS 或 RSS 暫時失敗仍可接續。每輪依最久未嘗試的順序處理，受頻道單輪上限約束。

長摘要會自動拆成多則 Telegram 訊息，每段成功後保存進度，重跑只續傳未完成段落。Telegram 已收件但本機尚未記錄／GitHub 尚未回存就中斷時，仍可能重複發送。未完成紀錄不會清除；完成紀錄保留最近 300 筆（沿用 `YT_MAX_SEEN_IDS`）。既有已讀清單照常使用，升級不回播舊影片；舊版未保存失敗原因，因此無法自動回補升級前缺少的摘要或查證。

頻道設定範例：

```json
[
  {
    "name": "加密龐克",
    "channel_id": "UCeeeGbipVKpz23A8_c3I3uA",
    "system_prompt": "以 HEIMDALL 的口吻說明",
    "max_new_per_run": 3
  }
]
```

`name` 必須唯一，`channel_id` 是 YouTube 頻道 ID；`system_prompt` 可選，用來補充該頻道的摘要風格。去重狀態存在 `data/yt_seen_ids.json`，在 GitHub Actions 上會由 workflow 自動 commit 回 repo（見下方「狀態持久化」）。

---

## 快速開始

### 1. 下載 / Fork 專案

```bash
git clone https://github.com/Yili-code/Crypto-Flash.git
cd Crypto-Flash
```

### 2. 設定環境變數

複製 `.env.example` 成為 `.env`，並填入你的設定：

```env
TELEGRAM_BOT_TOKEN_01=""
TELEGRAM_BOT_TOKEN_02=""
TELEGRAM_CHAT_ID=""
GEMINI_API_KEY=""
GEMINI_MODEL="gemini-3.5-flash-lite"
```

Bot 01 用於 Jin10 推播、新聞指令、事件追蹤、AI 問答與日報；Bot 02 只用於 YouTube。只使用新聞查詢、日報或事件追蹤時不需要 Gemini key，但必須已有保存的新聞資料。`TELEGRAM_CHAT_ID` 同時限制問答服務接受訊息的聊天室。請在專案根目錄執行下列命令，使用 Python 3.12；監控與問答需分別在兩個終端機啟動。

### 3. 安裝依賴

```bash
pip install -r requirements.txt
```

### 4. 啟動監控腳本

```bash
python src/jin10_monitor.py
```

### 5. 同時啟動監控與 Telegram 問答（取代步驟 4）

```bash
python src/flash_service.py
```

在群組中可直接 @ 機器人或使用 `/ask`；私人聊天則可直接輸入問題。

### 新聞查詢與每日重點

| Telegram 指令 | 用途 |
|---|---|
| `/digest` | 昨日重點，按 CRITICAL、HIGH、MEDIUM 排序，最多列出 8 則 |
| `/digest today` | 今日截至目前的重點 |
| `/digest YYYY-MM-DD` | 指定日期的重點，限保存的資料 |
| `/news`、`/news 10` | 最近 5 則或 10 則快訊，最多 10 則 |
| `/search BTC` | 不分大小寫搜尋近期新聞的標題與內文；多字搜尋採完整詞組比對 |
| `/important`、`/important 10` | 只查看 HIGH、CRITICAL 快訊 |
| `/status` | 可查詢筆數、分級分布、最新紀錄時間 |
| `/help`、`/start` | 顯示指令說明 |

這些指令不需要 Gemini API key，群組中也可使用 `/digest@你的機器人名稱`。`/news`、`/search`、`/important` 顯示來源摘錄；`/digest` 沿用監控時已產生的 AI 摘要，依重要性彙整，不增加模型呼叫，不把未分級原文當成摘要推送。Telegram 問答服務必須正在執行，才能回覆指令。問答 workflow 與 Jin10 monitor 一樣，每 6 小時啟動、服務執行 350 分鐘後停止，留時間在 360 分鐘 job 上限前保存追蹤進度，接近全天運行。兩次執行間仍有空窗，GitHub 排程延遲也可能延長空窗，並非無縫 24/7。每日推送是獨立 workflow，不受問答服務是否啟動影響。

**每日推送：** `daily_digest.yml` 設定於台灣時間 **08:15** 推送前一日 00:00–24:00 的重點，使用 `TELEGRAM_BOT_TOKEN_01` 與 `TELEGRAM_CHAT_ID`。日期按新聞收錄時間、UTC+8 計算。第一次啟用必須先讓監控累積資料；缺少資料會明確說明，並不代表當天沒有事件。日報再經 AI 合併同題新聞，以「一句主軸＋最多三件大事＋後續焦點」呈現，正文最多 250 字；AI 整理失敗會明確通知，不回退成長篇摘錄。設定與限制見 [每日重點說明](daily-digest.md)。

日報另用 `data/news_archive.json` 保存最近 **72 小時、最多 5,000 則**，不改變問答背景原本 6 小時的範圍。日報會標示收錄起迄時間，但不保證資料完整。GitHub Actions 的問答與日報只讀取 checkout 時已提交的資料，監控執行中的更新尚未同步；`/status` 顯示的是資料新鮮度，並非連線健康檢查。

`data/daily_digest_state.json` 記錄最近成功送出的日期，同一天重新執行會跳過；發送失敗不更新狀態。若發送成功後程序中斷，或狀態無法提交，重跑仍可能重複送出，請先檢查紀錄。狀態檔損壞時會停止並回報錯誤。

排程需將 workflow 合併到 GitHub 預設分支後才會啟用，GitHub 排程可能延遲。也可手動觸發 workflow，或在本機執行 `python src/daily_digest.py`，後者會實際發送昨日報告。

### 如何選擇查詢方式

| 需求 | 指令與資料範圍 |
|---|---|
| 快速掃描最新消息 | `/news`、`/search`、`/important`：預設最近 6 小時、最多保存 80 則 |
| 查看一天的重點 | `/digest`：72 小時歷史資料中的指定日期，沿用既有摘要 |
| 回顧特定主題 | `/timeline 詞組`：72 小時歷史資料，不需先訂閱 |
| 接續上次閱讀 | `/track 詞組` 後使用 `/updates`：從訂閱後開始累積未讀進展 |
| 請 AI 解釋消息 | `/ask 問題`：預設帶入最近 40 則背景的標題或內文開頭，需要 Gemini |

區分這些範圍，能避免把短期搜尋沒有結果誤認成事件沒發生，也能用未讀進度減少重複閱讀。所有查詢都受已收錄資料限制，`/ask` 不會即時搜尋網路。

### 事件追蹤與後續進展

| Telegram 指令 | 用途 |
|---|---|
| `/track spot ETF` | 從加入時開始追蹤此完整詞組，不分大小寫 |
| `/tracks` | 列出追蹤主題及每個主題尚未讀取的紀錄數 |
| `/timeline spot ETF` | 回顧最近 72 小時的相關紀錄，最多顯示最新 8 則，按收錄時間排列 |
| `/updates` | 讀取所有追蹤主題的新進展，由舊到新、每次最多 8 則 |
| `/updates spot ETF` | 只讀取指定主題的新進展 |
| `/untrack spot ETF` | 停止追蹤，保留原有新聞資料 |

追蹤使用新聞標題、內文與既有摘要的**完整詞組比對**，不額外呼叫 Gemini，也不推測事件的因果關係。例如 `spot ETF` 不會自動匹配「現貨 ETF」；可分別加入兩個詞組。`/timeline` 不必先追蹤，也不影響未讀進度。輸出會區分摘要節錄與來源摘錄。

`/updates` 是主動查詢，不會額外自動推播。只有 Telegram 確認發送成功，才更新本次實際顯示的紀錄進度；超過筆數或訊息長度上限的進展會留待下一次讀取。一次查詢中，同一紀錄命中多個主題只顯示一次；指定主題查詢只更新該主題進度。新增主題不把加入前的紀錄當成未讀，可用 `/timeline` 回顧；重複加入同一詞組不會重設進度。

最多追蹤 **12 個主題**，每個詞組 **40 個字元**。設定的 `TELEGRAM_CHAT_ID` 聊天室共用一份清單與閱讀進度，聊天室內可發指令的成員都能管理它；未設定聊天室時，事件追蹤指令不開放。設定與進度保存在 `data/event_tracking.json`，由問答 workflow 單獨寫入並提交回 repository，因此也會受 repository 的可見性設定影響。本機可用 `EVENT_STATE_FILE` 指定其他保存位置。

歷史資料受既有 **72 小時、5,000 則**上限限制；太久未查詢的進展可能已過期。GitHub 上只能看到 checkout 時已保存的新聞；沒有新紀錄不代表外界沒有新進展。若 Telegram 已收到訊息，但本機寫入或 GitHub 保存進度失敗，下次查詢仍可能重複出現該紀錄。

### 6. 啟動 YouTube 監控（可選）

```bash
python src/yt_monitor.py
```

執行前請先在 `config/yt_channels.json` 填入要監控的頻道。這個腳本跑完目前設定的所有頻道後就會結束，適合搭配排程工具或 GitHub Actions 使用。

---

## GitHub Actions 部署

本專案已包含五個 workflow：

| Workflow | 作用 |
|---|---|
| `flash_monitor.yml` | 執行 `src/flash_service.py`，共用即時快訊供問答使用，監控快訊並推播 |
| `yt_monitor.yml` | 執行 `src/yt_monitor.py`，監控 YouTube 新影片並推播摘要 |
| `ci.yml` | push / PR 時執行 `ruff` 與 `pytest`，不使用任何 secret |
| `daily_digest.yml` | 每日台灣時間 08:15 推送昨日重點，保存送出日期以避免重複 |

在 GitHub 的 `Settings → Secrets and variables → Actions` 中新增：

| Secret / Variable | 說明 |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio 的 Gemini API 金鑰 |
| `TELEGRAM_BOT_TOKEN_01` | Telegram Bot Token |
| `TELEGRAM_BOT_TOKEN_02` | YouTube 監控使用的 Telegram Bot Token |
| `TELEGRAM_CHAT_ID` | 推播目標聊天室或群組 ID |
| `GEMINI_MODEL` | 可選，預設為 `gemini-3.5-flash-lite` |

`flash_monitor.yml` 會在每 6 小時排程一次；`yt_monitor.yml` 會在每小時的第 0 分與第 30 分執行一次。兩者都支援手動觸發 `workflow_dispatch`。

`GEMINI_MODEL` 請設為 Actions **Variable**；其餘表列金鑰與聊天室設定使用 **Secrets**。其他可調環境變數若要在 Actions 生效，需加入對應 workflow 的 `env`；僅新增 repository variable 不會自動傳給程式。

### 狀態持久化

`data/recent_news.json`（近期快訊上下文）與 `data/yt_seen_ids.json`（已推播影片）必須跨執行保留，否則問答會失去背景，YouTube 會重新預熱並略過當時 RSS 中的既有影片。

這兩個檔案、日報的 `data/news_archive.json`、`data/daily_digest_state.json`，以及追蹤設定 `data/event_tracking.json`，由 `.github/actions/persist-state` 於每次執行結束時 **commit 回 repo**。快訊監控會在 350 分鐘後正常停止，留時間在 job 上限前保存資料：

- 每個檔案只有一個 workflow 會寫入，所以遇到 push 競態時會把自己的版本重放到最新的 tip，不會覆蓋別的 workflow 的變更。
- 內容沒變就不會產生 commit；commit 訊息帶 `[skip ci]`，`ci.yml` 也忽略 `data/**`。
- 寫入的 workflow 需要 `permissions: contents: write`。若你的 repo 設定為唯讀的 `GITHUB_TOKEN`，請在 `Settings → Actions → General → Workflow permissions` 改為 **Read and write permissions**。

> 早期版本改用 GitHub Actions cache 保存這兩個檔案。cache 會在 7 天未使用後被淘汰、以 key 前綴模糊比對（曾因此還原到錯誤的項目），而且無法檢視內容，因此改為直接 commit。

---

## 可調整環境變數

### 共用設定

| 變數 | 預設值 | 用途 |
|---|---|---|
| `TELEGRAM_BOT_TOKEN_01` | 空 | Telegram Bot Token |
| `TELEGRAM_CHAT_ID` | 空 | 推播目標 / 問答來源限制 |
| `TELEGRAM_MIN_SEND_INTERVAL` | `3.5` | 兩則推播之間的最小間隔秒數，用來避開 Telegram 的 429 限流 |
| `TELEGRAM_MAX_RETRY_AFTER` | `30` | 收到 429 時最多等待的秒數（Telegram 有時會要求數百秒） |
| `GEMINI_API_KEY` | 空 | Gemini API 金鑰 |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | 生成模型 |
| `NEWS_CONTEXT_FILE` | `data/recent_news.json` | 近期快訊的共用上下文檔 |
| `CONTEXT_MAX_AGE_SEC` | `21600` | 近期訊息保留秒數 |

### 監控腳本設定

| 變數 | 預設值 | 用途 |
|---|---|---|
| `MAX_TIER_TO_SEND` | `MEDIUM` | 推播門檻，達到或高於此等級才送出 |
| `KEYWORDS_FILE` | 空 | 自訂關鍵字檔案路徑 |
| `WS_URLS` | `wss://wss-flash-2.jin10.com/` | Jin10 WebSocket 端點 |
| `WS_IDLE_TIMEOUT` | `180` | 若長時間無訊息就重連 |
| `WS_RECONNECT_DELAY` | `5` | 重連前等待秒數 |
| `CONTEXT_MAX_ITEMS` | `80` | 近期訊息最多保留數量 |
| `OUTBOX_MAXSIZE` | `200` | 待處理快訊佇列上限；滿了會丟棄最舊的一則，確保接收迴圈不被阻塞 |
| `GEMINI_RECONNECT_DELAY` | `30` | Gemini 不可用時的背景重試間隔秒數，最小為 1 秒 |
| `NEWS_ARCHIVE_FILE` | `data/news_archive.json` | 日報新聞保存位置，保留最近 72 小時、最多 5,000 則 |
| `DIGEST_STATE_FILE` | `data/daily_digest_state.json` | 日報最近成功送出日期；由日報腳本寫入 |

### 問答腳本設定

| 變數 | 預設值 | 用途 |
|---|---|---|
| `CONTEXT_SNIPPET_LIMIT` | `40` | 回答問題時帶入的背景訊息數量 |
| `EVENT_STATE_FILE` | `data/event_tracking.json` | 聊天室共用的事件追蹤清單與閱讀進度 |

### YouTube 監控設定

| 變數 | 預設值 | 用途 |
|---|---|---|
| `TELEGRAM_BOT_TOKEN_02` | 空 | YouTube 摘要推播使用的 Telegram Bot Token |
| `YT_CHANNELS_CONFIG` | `config/yt_channels.json` | YouTube 頻道設定檔路徑 |
| `YT_MAX_NEW_PER_RUN` | `3` | 頻道未指定上限時，單次最多嘗試的待處理影片數，包含重試；其餘保留 |
| `YT_SEEN_STATE_FILE` | `data/yt_seen_ids.json` | 已處理影片 ID 的狀態檔路徑 |
| `YT_PROGRESS_FILE` | `data/yt_progress.json` | 通知、摘要、查證與分段送達進度；自訂路徑需同步調整 workflow 保存清單 |
| `YT_SCHEDULE_FILE` | `data/yt_schedule.json` | 下次輪流處理的起始頻道；自訂路徑需同步調整 workflow 保存清單 |
| `YT_RUN_BUDGET_SECONDS` | `1260` | 本輪處理時間上限；需小於 workflow 的 24 分鐘外部停止時間以保留回存時間 |
| `YT_MAX_SEEN_IDS` | `300` | 每個頻道最多保留的已處理影片 ID 數量 |

---

## 開發與測試

```bash
pip install -r requirements-dev.txt
pytest          # 單元測試，全程不連網
ruff check .    # 靜態檢查
```

測試涵蓋 Jin10 快訊解析與 WebSocket 二進位協定、推播佇列的背壓行為、Telegram 送出的重試與限流邏輯、YouTube RSS 解析與去重狀態機，以及問答的提問判定。此外涵蓋新聞查詢、日報日期與摘要去重、日報送出狀態、事件追蹤的未讀進度與發送確認，以及 Gemini 故障恢復。測試不需要任何 API 金鑰，也不會發出任何網路請求。

---

## 重要說明

- 本專案僅供技術研究、個人資訊追蹤與學習使用。
- 抓取內容仍屬 Jin10 原資料來源所有。
- Gemini 生成的回答僅為輔助分析，不構成投資建議。
- 即時行情與訊息可能變動，請以官方資訊與實際市場為準。

## 免責聲明

AI 生成的摘要與分析僅供參考，不構成任何投資建議。市場有風險，投資前請自行評估與查證。

<div align="center">

<b>如果這個專案有幫你節省看新聞的時間，歡迎給個星號支持。</b>

</div>
