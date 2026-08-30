<div align="center">

# Jin10 News Scraper

**Completely Free x Actively Developed**

A serverless assistant that watches the Jin10 (金十數據) WebSocket feed 24/7. When a news item matches your keywords, it gets summarized by Gemini and pushed straight to your Telegram — instantly (keywords are fully customizable). You can also ask it questions directly in Telegram, and it will answer using the recent news it has been monitoring.

Runs 24/7 via GitHub Actions, and works fine in both groups and DMs.

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
<img src="assets/demo001.jpg" width="100%"><br>
<sub><b>Tiered Push Notifications</b><br>Gemini ranks each news item by importance</sub>
</td>
<td align="center" width="33%">
<img src="assets/demo002.jpg" width="100%"><br>
<sub><b>AI Real-time Q&A</b><br>Combines pushed news history with its own reasoning</sub>
</td>
</tr>
</table>
</div>

## What is this

Jin10 fires off hundreds to thousands of flash news items every day, and roughly 90% of it is noise. This script connects directly to Jin10's private WebSocket protocol, parses every message, and **only acts when a message matches keywords you care about**: it hands only the relevant item to Gemini, then automatically and instantly pushes the result to Telegram.

No polling, no delay, no server bill — everything runs on GitHub Actions, completely free, always-on, and self-restarting.

All you have to do is wait for the notification on your phone — and if that's not enough, you can follow up directly in Telegram, e.g. "What does this news mean for BTC in the short term?", and it will give you a supplementary analysis based on the context of the news it has recently monitored.

## Why it's worth a look

- **Not scraping, a real connection** — reverse-engineered Jin10's binary WebSocket protocol (XOR encryption, custom packet format), not a laggy RSS feed or polling API.

- **Keyword-ready out of the box** — comes with a built-in keyword library covering geopolitics, central bank moves, commodities, and crypto; or you can supply your own fully custom `.txt` file.

- **Not a translation, a briefing** — Gemini isn't just "translating," it runs on a persona-based prompt (think Jarvis from Iron Man), producing structured output covering macroeconomic impact, crypto short/long-term trends, and key term explanations — ready to read at a glance.

- **Not just push, you can also ask** — a separate script, `telegram_qa.py`, lets you ask the bot questions directly in Telegram; it pulls in the flash news it has monitored over the past few hours as background context before answering. No `@` needed in DMs; in groups, mention `@your_bot_username explain PCE's impact on rate hikes/cuts` or use the `/ask` command (see example image above). It runs as a completely separate process from the monitoring script, so the two don't interfere with each other.

- **Zero infrastructure** — no database, no cloud host, no Docker. The whole system is one `.py` file plus one workflow file.

- **Self-healing, always-on** — automatically reconnects on disconnect; wraps up cleanly before GitHub Actions times out, and the next scheduled run picks up seamlessly, so in theory it can run uninterrupted 24/7.

## How it works

```
Jin10 WebSocket ──▶ Parse binary packets ──▶ Keyword matching

                                          │ Match
                                          ▼
                                    Gemini tiering + summary + filtering

                                          │
                              ┌───────────┴───────────┐
                              ▼                        ▼
                       Instant Telegram push      Write to recent_news.json

                                                        │
                                                        ▼
                                          telegram_qa.py runs continuously in background

                                                        │
                        Telegram message ──▶ Detect if it's a question ──▶ Gemini answers ──▶ Reply
```

`jin10_monitor.py` (monitoring + push) runs as a single GitHub Actions job, restarted every 6 hours via cron; if it disconnects mid-run, the script itself auto-reconnects, no manual intervention needed.

### Two independent processes

The project is split into two independent scripts that can be deployed and restarted separately:

| Script | Responsibility | Trigger |
|---|---|---|
| `jin10_monitor.py` | Connects to the Jin10 WebSocket, matches keywords, has Gemini tier and summarize, pushes to Telegram | Runs continuously |
| `telegram_qa.py` | Polls Telegram's `getUpdates`, detects whether a message is a question, calls Gemini to answer | Runs continuously |

The two scripts exchange "recent news" through a shared file, `recent_news.json` (`NEWS_CONTEXT_FILE`): every time `jin10_monitor.py` finishes evaluating a news item, it writes the recent record to this file; before answering a question, `telegram_qa.py` reads it to build background context. As long as both scripts read/write the same file (same machine / same persistent storage), one restarting or temporarily going down won't affect the other. If `telegram_qa.py` can't find the file, it will still answer normally, just without recent news context.

## Quick Start

### 1. Fork / Clone this repo

### 2. Set up Secrets

Go to the repo's `Settings → Secrets and variables → Actions` and add:

| Secret Name | Description |
|---|---|
| `GEMINI_API_KEY` | Gemini API key from Google AI Studio |
| `TELEGRAM_BOT_TOKEN` | Bot token created via [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | The channel / group / individual Chat ID that should receive pushes |

### 3. (Optional) Customize keywords

Create a plain text file with one keyword per line, and set the `KEYWORDS_FILE` environment variable in the workflow to point to it. Leave it empty to use the built-in keyword library.

### 4. Open Actions

After forking, go to the `Actions` tab and manually trigger `workflow_dispatch` once, or wait for the scheduled run to trigger automatically. On first startup, the script validates the Gemini API key and reports the result in the logs.

### 5. (Optional) Enable Telegram Q&A

If you want to ask the bot questions directly in Telegram, start `telegram_qa.py` separately (you can reuse the same set of Secrets, run it as an extra job/schedule, or on any machine that can keep a Python process running). It's a separate process from the monitoring script, so restarting one doesn't affect the other; as long as both can read/write the same `recent_news.json`, Q&A will automatically pull in recently monitored news as context.

## Environment Variables

### Shared (read by both scripts)

| Variable | Default | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | Telegram Bot Token |
| `TELEGRAM_CHAT_ID` | — | Push target / allowed Chat ID for Q&A (leave empty in `telegram_qa.py` to not restrict source chat) |
| `GEMINI_API_KEY` | — | Gemini API key |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Model used |
| `NEWS_CONTEXT_FILE` | `recent_news.json` | Shared file path the two scripts use to exchange "recent news" |
| `CONTEXT_MAX_AGE_SEC` | `21600` (6 hours) | How long recent news is retained before it's excluded from Q&A context |

### `jin10_monitor.py`-specific

| Variable | Default | Purpose |
|---|---|---|
| `MAX_TIER_TO_SEND` | `MEDIUM` | Push threshold — only news rated by Gemini at this importance level or higher gets pushed (`CRITICAL`/`HIGH`/`MEDIUM`/`LOW`) |
| `KEYWORDS_FILE` | empty | Path to a custom keyword list; leave empty to use the built-in keyword library |
| `WS_URLS` | `wss://wss-flash-2.jin10.com/` | Jin10 WebSocket endpoint(s); comma-separate multiple for rotation |
| `WS_IDLE_TIMEOUT` | `180` | Seconds without a message before it's considered disconnected and reconnects |
| `WS_RECONNECT_DELAY` | `5` | Seconds to wait before reconnecting |
| `CONTEXT_MAX_ITEMS` | `80` | Maximum number of recent news items retained in the context file |

### `telegram_qa.py`-specific

| Variable | Default | Purpose |
|---|---|---|
| `CONTEXT_SNIPPET_LIMIT` | `40` | Maximum number of recent news items included as context when answering a question |

## Disclaimer

This project is for technical learning and personal information organization purposes only. Copyright of the scraped content belongs to Jin10 Data (金十數據). The AI-generated analysis is only a machine-generated summary and **does not constitute investment advice**. Markets carry risk; please verify independently before making any decisions.

<div align="center">

<b>If this saves you time scrolling for news, consider giving it a star</b>

</div>