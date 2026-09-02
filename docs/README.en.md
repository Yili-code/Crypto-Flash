<div align="center">

# Jin10 News Scraper

**Free x Always-on**

This project continuously watches the Jin10 WebSocket feed. When a news item matches your keywords, Gemini grades and summarizes it, then the result is pushed to Telegram. You can also ask questions directly in Telegram, and the bot will use recent monitored flash news as background context.

[![GitHub Actions](https://img.shields.io/badge/Automation-GitHub%20Actions-2088FF?logo=githubactions&logoColor=white)](.)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](.)
[![Gemini](https://img.shields.io/badge/AI-Gemini-8E75B2?logo=googlegemini&logoColor=white)](.)
[![Telegram](https://img.shields.io/badge/Push-Telegram-26A5E4?logo=telegram&logoColor=white)](.)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**English | [繁體中文](README.md)**

</div>

<div align="center">
<table>
<tr>
<td align="center" width="33%">
<img src="../assets/demo001.jpg" width="100%"><br>
<sub><b>Tiered Push</b><br>Gemini grades the event by importance</sub>
</td>
<td align="center" width="33%">
<img src="../assets/demo002.jpg" width="100%"><br>
<sub><b>AI Real-time Q&A</b><br>Uses recent flash news as answer context</sub>
</td>
</tr>
</table>
</div>

---

## Project overview

This is a GitHub Actions-driven automation project for tracking and filtering Jin10 flash news, keeping only the items that matter most.

### What it does

- Connects directly to Jin10 WebSocket feeds
- Parses messages and removes noise with keyword filtering
- Sends relevant items to Gemini for grading and summary
- Pushes important updates to Telegram
- Adds a Telegram Q&A mode with recent context memory

---

## Features

- WebSocket monitor with auto-reconnect: `src/jin10_monitor.py`
- Keyword filtering with built-in defaults and optional `KEYWORDS_FILE`
- Gemini grading and summary logic: `src/gemini.py`
- Telegram push messaging: `src/tg01.py`
- Telegram Q&A listener: `src/telegram_qa.py`
- Shared recent-news context: `data/recent_news.json`
- Scheduled execution via GitHub Actions every 6 hours

---

## How it works

```text
Jin10 WebSocket
   ↓
Binary packet parsing
   ↓
Keyword matching
   ↓
Gemini tiering + summarization
   ↓
Telegram push
   ↓
Save to data/recent_news.json
   ↓
telegram_qa.py answers questions using recent context
```

`jin10_monitor.py` and `telegram_qa.py` run as separate processes and share the same `recent_news.json` file for context.

---

## Quick start

### 1. Clone or fork the repo

```bash
git clone https://github.com/<your-user>/<your-repo>.git
cd jin10_news_scraper
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in the values:

```env
TELEGRAM_BOT_TOKEN_01=""
TELEGRAM_CHAT_ID=""
GEMINI_API_KEY=""
GEMINI_MODEL="gemini-3.5-flash-lite"
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the monitor

```bash
python src/jin10_monitor.py
```

### 5. Run the Telegram Q&A bot (optional)

```bash
python src/telegram_qa.py
```

In a Telegram group, you can mention the bot or use `/ask`; in private chat, you can send a question directly.

---

## GitHub Actions deployment

This project includes two workflows:

| Workflow | Purpose |
|---|---|
| `flash_monitor.yml` | Runs `src/jin10_monitor.py` on a schedule and pushes filtered news |
| `telegram_qa.yml` | Runs `src/telegram_qa.py` to answer Telegram questions |

Set these in GitHub `Settings → Secrets and variables → Actions`:

| Secret / Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Gemini API key |
| `TELEGRAM_BOT_TOKEN_01` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Target chat ID for pushes |
| `GEMINI_MODEL` | Optional; defaults to `gemini-3.5-flash-lite` |

The monitor workflow runs every 6 hours and also supports manual `workflow_dispatch`.

---

## Configurable environment variables

### Shared settings

| Variable | Default | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN_01` | empty | Telegram Bot Token |
| `TELEGRAM_CHAT_ID` | empty | Push target / source chat guard for Q&A |
| `GEMINI_API_KEY` | empty | Gemini API key |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Model to use |
| `NEWS_CONTEXT_FILE` | `data/recent_news.json` | Shared recent-news cache |
| `CONTEXT_MAX_AGE_SEC` | `21600` | Max age for background context |

### Monitor settings

| Variable | Default | Purpose |
|---|---|---|
| `MAX_TIER_TO_SEND` | `MEDIUM` | Only send pushes when the Gemini tier meets this threshold |
| `KEYWORDS_FILE` | empty | Optional custom keyword file |
| `WS_URLS` | `wss://wss-flash-2.jin10.com/` | Jin10 WebSocket endpoint |
| `WS_IDLE_TIMEOUT` | `180` | Reconnect if no traffic is seen |
| `WS_RECONNECT_DELAY` | `5` | Delay before reconnect |
| `CONTEXT_MAX_ITEMS` | `80` | Max recent items retained |

### Q&A settings

| Variable | Default | Purpose |
|---|---|---|
| `CONTEXT_SNIPPET_LIMIT` | `40` | Number of recent items included in the answer prompt |

---

## Important notes

- This project is meant for technical learning, monitoring, and personal research.
- The scraped content remains the property of Jin10.
- Gemini-generated summaries are auxiliary analysis and not investment advice.
- Final decisions should be based on official releases and current market conditions.

## Disclaimer

AI-generated summaries and analysis are for reference only and do not constitute investment advice. Markets are risky; do your own research before making financial decisions.

<div align="center">

<b>If this project saved you time filtering market noise, consider giving it a star.</b>

</div>
