<div align="center">

# Jin10 News Scraper

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

---

## 主要功能

- WebSocket 連線與自動重連：`src/jin10_monitor.py`
- 關鍵字過濾：支援內建關鍵字清單，也可用 `KEYWORDS_FILE` 自訂
- Gemini 分級與摘要：`src/gemini.py`
- Telegram 推播：`src/tg01.py`
- Telegram 對話問答：`src/telegram_qa.py`
- 共享近期新聞上下文：`data/recent_news.json`
- GitHub Actions 自動執行：每 6 小時排程一次，支援手動觸發

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
telegram_qa.py 依背景資料回答 Telegram 問題
```

`jin10_monitor.py` 和 `telegram_qa.py` 是兩個獨立流程，共同使用 `recent_news.json` 作為近期快訊上下文。

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
TELEGRAM_BOT_TOKEN=""
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
python src/telegram_qa.py
```

在群組中可直接 @ 機器人或使用 `/ask`；私人聊天則可直接輸入問題。

---

## GitHub Actions 部署

本專案已包含兩個 workflow：

| Workflow | 作用 |
|---|---|
| `flash_monitor.yml` | 執行 `src/jin10_monitor.py`，監控快訊並推播 |
| `telegram_qa.yml` | 執行 `src/telegram_qa.py`，接收 Telegram 問題並回答 |

在 GitHub 的 `Settings → Secrets and variables → Actions` 中新增：

| Secret / Variable | 說明 |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio 的 Gemini API 金鑰 |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token |
| `TELEGRAM_CHAT_ID` | 推播目標聊天室或群組 ID |
| `GEMINI_MODEL` | 可選，預設為 `gemini-3.5-flash-lite` |

`flash_monitor.yml` 會在每 6 小時排程一次，也支援手動觸發 `workflow_dispatch`。

---

## 可調整環境變數

### 共用設定

| 變數 | 預設值 | 用途 |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | 空 | Telegram Bot Token |
| `TELEGRAM_CHAT_ID` | 空 | 推播目標 / 問答來源限制 |
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

### 問答腳本設定

| 變數 | 預設值 | 用途 |
|---|---|---|
| `CONTEXT_SNIPPET_LIMIT` | `40` | 回答問題時帶入的背景訊息數量 |

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
