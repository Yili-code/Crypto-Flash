<div align="center">

# Crypto Flash

**免費 x 持續運行中**

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
- 監控 YouTube 頻道 RSS，新影片交給 Gemini 整理 5 個重點後推播到 Telegram

---

## 主要功能

- WebSocket 連線與自動重連：`src/jin10_monitor.py`
- 關鍵字過濾：支援內建關鍵字清單，也可用 `KEYWORDS_FILE` 自訂
- Gemini 分級與摘要：`src/gemini.py`
- Telegram 推播：`src/tg.py`
- Telegram 對話問答：`src/telegram_assistant.py`
- YouTube 新影片監控與摘要：`src/yt_monitor.py`
- 共享近期新聞上下文：`data/recent_news.json`
- GitHub Actions 自動執行：Jin10 每 6 小時一次，YouTube 每 30 分鐘一次，皆支援手動觸發

---

## 工作流程

```text
Jin10 WebSocket
   ↓
解析二進位封包
   ↓
關鍵字比對
   ↓
Gemini 分級 + 摘要
   ↓
Telegram 推播
   ↓
寫入 data/recent_news.json
   ↓
telegram_assistant.py 依背景資料回答 Telegram 問題
```

`jin10_monitor.py` 和 `telegram_assistant.py` 是兩個獨立流程，共同使用 `recent_news.json` 作為近期快訊上下文。

Gemini 啟動檢查或執行中的摘要請求失敗時，快訊監控會暫停推播並在背景每 30 秒重新檢查連線，成功後自動恢復摘要推播。中斷期間仍接收快訊並保存符合關鍵字的新聞背景，不會改推原文；這些已略過的新聞不會在恢復後補發。未設定 API key 時也會暫停推播。這項恢復機制與 Jin10 WebSocket 原有的斷線重連分開運作。

### YouTube 影片監控

`yt_monitor.py` 會讀取 `config/yt_channels.json` 中的頻道，透過 YouTube RSS 找出新影片，再依序執行以下流程：

```text
YouTube RSS
   ↓
依 channel_id 解析影片
   ↓
比對 data/yt_seen_ids.json 去重
   ↓
Gemini 觀看影片並整理 5 個重點
   ↓
Telegram 推播摘要與來源連結
```

首次執行某個頻道時，程式只會把 RSS 中現有影片寫入 `data/yt_seen_ids.json` 作為預熱，不會推播既有影片。之後每次執行最多處理該頻道 `max_new_per_run` 部新影片；超過上限的較舊影片會標記為已讀但不推播。即使 Gemini 摘要失敗，仍會推送影片連結。

頻道設定範例：

```json
[
  {
    "name": "加密龐克",
    "channel_id": "UCeeeGbipVKpz23A8_c3I3uA",
    "system_prompt": "以 JARVIS 的口吻說明",
    "max_new_per_run": 3
  }
]
```

`name` 必須唯一，`channel_id` 是 YouTube 頻道 ID；`system_prompt` 可選，用來補充該頻道的摘要風格。去重狀態存在 `data/yt_seen_ids.json`，在 GitHub Actions 上會由 workflow 自動 commit 回 repo（見下方「狀態持久化」）。

---

## 快速開始

### 1. 下載 / Fork 專案

```bash
git clone https://github.com/<your-user>/<your-repo>.git
cd jin10_news_scraper
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

### 3. 安裝依賴

```bash
pip install -r requirements.txt
```

### 4. 啟動監控腳本

```bash
python src/jin10_monitor.py
```

### 5. 啟動 Telegram 問答腳本（可選）

```bash
python src/telegram_assistant.py
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

這些指令不需要 Gemini API key，群組中也可使用 `/digest@你的機器人名稱`。`/news`、`/search`、`/important` 顯示來源摘錄；`/digest` 沿用監控時已產生的 AI 摘要，依重要性彙整，不增加模型呼叫，不把未分級原文當成摘要推送。Telegram 問答服務必須正在執行，才能回覆指令。目前問答 workflow 每 6 小時啟動、最多執行 15 分鐘；若需要持續回應，可持續執行本機 `telegram_assistant.py`。每日推送是獨立 workflow，不受問答服務是否啟動影響。

**每日推送：** `daily_digest.yml` 設定於台灣時間 **08:15** 推送前一日 00:00–24:00 的重點，使用 `TELEGRAM_BOT_TOKEN_01` 與 `TELEGRAM_CHAT_ID`。日期按新聞收錄時間、UTC+8 計算。第一次啟用必須先讓監控累積資料；缺少資料會明確說明，並不代表當天沒有事件。日報逐則節錄既有摘要，並非新增一篇跨事件推論文章。

日報另用 `data/news_archive.json` 保存最近 **72 小時、最多 5,000 則**，不改變問答背景原本 6 小時的範圍。日報會標示收錄起迄時間，但不保證資料完整。GitHub Actions 的問答與日報只讀取 checkout 時已提交的資料，監控執行中的更新尚未同步；`/status` 顯示的是資料新鮮度，並非連線健康檢查。

`data/daily_digest_state.json` 記錄最近成功送出的日期，同一天重新執行會跳過；發送失敗不更新狀態。若發送成功後程序中斷，或狀態無法提交，重跑仍可能重複送出，請先檢查紀錄。狀態檔損壞時會停止並回報錯誤。

排程需將 workflow 合併到 GitHub 預設分支後才會啟用，GitHub 排程可能延遲。也可手動觸發 workflow，或在本機執行 `python src/daily_digest.py`，後者會實際發送昨日報告。

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
| `flash_monitor.yml` | 執行 `src/jin10_monitor.py`，監控快訊並推播 |
| `telegram_assistant.yml` | 執行 `src/telegram_assistant.py`，接收 Telegram 問題並回答 |
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

### 狀態持久化

`data/recent_news.json`（近期快訊上下文）與 `data/yt_seen_ids.json`（已推播影片）必須跨執行保留，否則問答會失去背景、YouTube 會重複推播同一批影片。

這兩個檔案，以及日報的 `data/news_archive.json`、`data/daily_digest_state.json`，由 `.github/actions/persist-state` 於每次執行結束時 **commit 回 repo**。快訊監控會在 350 分鐘後正常停止，留時間在 job 上限前保存資料：

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

### YouTube 監控設定

| 變數 | 預設值 | 用途 |
|---|---|---|
| `TELEGRAM_BOT_TOKEN_02` | 空 | YouTube 摘要推播使用的 Telegram Bot Token |
| `YT_CHANNELS_CONFIG` | `config/yt_channels.json` | YouTube 頻道設定檔路徑 |
| `YT_MAX_NEW_PER_RUN` | `3` | 頻道未指定上限時，單次最多處理的新影片數 |
| `YT_SEEN_STATE_FILE` | `data/yt_seen_ids.json` | 已處理影片 ID 的狀態檔路徑 |
| `YT_MAX_SEEN_IDS` | `300` | 每個頻道最多保留的已處理影片 ID 數量 |

---

## 開發與測試

```bash
pip install -r requirements-dev.txt
pytest          # 單元測試，全程不連網
ruff check .    # 靜態檢查
```

測試涵蓋 Jin10 快訊解析與 WebSocket 二進位協定、推播佇列的背壓行為、Telegram 送出的重試與限流邏輯、YouTube RSS 解析與去重狀態機，以及問答的提問判定。測試不需要任何 API 金鑰，也不會發出任何網路請求。

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
