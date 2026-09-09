<div align="center">

# Crypto Flash

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
- Monitors YouTube channel RSS feeds, summarizes new videos into five key points, and pushes them to Telegram

---

## Features

- WebSocket monitor with auto-reconnect: `src/jin10_monitor.py`
- Keyword filtering with built-in defaults and optional `KEYWORDS_FILE`
- Gemini grading and summary logic: `src/gemini.py`
- Telegram push messaging: `src/tg.py`
- Telegram Q&A listener: `src/telegram_assistant.py`
- YouTube video monitoring and summaries: `src/yt_monitor.py`
- Shared recent-news context: `data/recent_news.json`
- Scheduled execution via GitHub Actions: Jin10 every 6 hours and YouTube every 30 minutes

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
telegram_assistant.py answers questions using recent context
```

`jin10_monitor.py` and `telegram_assistant.py` run as separate processes and share the same `recent_news.json` file for context.

### YouTube video monitor

`yt_monitor.py` reads the channels in `config/yt_channels.json`, checks their YouTube RSS feeds for new videos, and processes them in order:

```text
YouTube RSS
   ↓
Parse videos by channel_id
   ↓
Deduplicate with data/yt_seen_ids.json
   ↓
Gemini watches the video and writes five key points
   ↓
Push the summary and source link to Telegram
```

The first run for each channel only warms up `data/yt_seen_ids.json` with the videos already in the RSS feed; it does not send notifications for existing videos. Later runs process at most `max_new_per_run` new videos per channel. Older videos beyond that limit are marked as seen without being pushed. If Gemini summarization fails, the monitor still sends the video link.

Example channel configuration:

```json
[
  {
    "name": "Crypto Punk",
    "channel_id": "UCeeeGbipVKpz23A8_c3I3uA",
    "system_prompt": "以 JARVIS 的口吻說明",
    "max_new_per_run": 3
  }
]
```

`name` must be unique, and `channel_id` is the YouTube channel ID. `system_prompt` is optional and can customize the summary style for a channel. Deduplication state lives in `data/yt_seen_ids.json`; on GitHub Actions the workflow commits it back to the repository automatically (see "State persistence" below).

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
TELEGRAM_BOT_TOKEN_02=""
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
python src/telegram_assistant.py
```

In a Telegram group, you can mention the bot or use `/ask`; in private chat, you can send a question directly.

### 6. Run the YouTube monitor (optional)

```bash
python src/yt_monitor.py
```

Before running it, add the channels to `config/yt_channels.json`. The script processes all configured channels once and then exits, so it is intended to be used with a scheduler or GitHub Actions.

---

## GitHub Actions deployment

This project includes four workflows:

| Workflow | Purpose |
|---|---|
| `flash_monitor.yml` | Runs `src/jin10_monitor.py` on a schedule and pushes filtered news |
| `telegram_assistant.yml` | Runs `src/telegram_assistant.py` to answer Telegram questions |
| `yt_monitor.yml` | Runs `src/yt_monitor.py` to monitor YouTube videos and push summaries |
| `ci.yml` | Runs `ruff` and `pytest` on push / PR; uses no secrets |

Set these in GitHub `Settings → Secrets and variables → Actions`:

| Secret / Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Gemini API key |
| `TELEGRAM_BOT_TOKEN_01` | Telegram bot token |
| `TELEGRAM_BOT_TOKEN_02` | Telegram bot token used by the YouTube monitor |
| `TELEGRAM_CHAT_ID` | Target chat ID for pushes |
| `GEMINI_MODEL` | Optional; defaults to `gemini-3.5-flash-lite` |

The Jin10 monitor workflow runs every 6 hours. `yt_monitor.yml` runs at minute 0 and minute 30 of every hour. Both workflows support manual `workflow_dispatch`.

### State persistence

`data/recent_news.json` (recent flash-news context) and `data/yt_seen_ids.json` (already-pushed videos) have to survive between runs. Without that the Q&A bot loses its background context and the YouTube monitor re-pushes the same videos on every run.

Both files are **committed back to the repository** by `.github/actions/persist-state` at the end of each run:

- Each file has exactly one writing workflow, so on a push race the writer replays its own copy on top of the current tip instead of clobbering another workflow's changes.
- Nothing is committed when the content did not change. Commit messages carry `[skip ci]`, and `ci.yml` ignores `data/**`.
- The writing workflows need `permissions: contents: write`. If your repository is configured with a read-only `GITHUB_TOKEN`, switch `Settings → Actions → General → Workflow permissions` to **Read and write permissions**.

> An earlier version kept these files in the GitHub Actions cache. Cache entries are evicted after 7 days of no use, are matched by key prefix (which silently restored the wrong entry), and cannot be inspected — hence the move to plain commits.

---

## Configurable environment variables

### Shared settings

| Variable | Default | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN_01` | empty | Telegram Bot Token |
| `TELEGRAM_CHAT_ID` | empty | Push target / source chat guard for Q&A |
| `TELEGRAM_MIN_SEND_INTERVAL` | `3.5` | Minimum seconds between two pushes, to stay under Telegram's rate limit |
| `TELEGRAM_MAX_RETRY_AFTER` | `30` | Cap on the 429 backoff (Telegram sometimes asks for several minutes) |
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
| `OUTBOX_MAXSIZE` | `200` | Pending-item queue size; the oldest is dropped when full so the receive loop never blocks |
| `GEMINI_RECONNECT_DELAY` | `30` | Background retry interval in seconds while Gemini is unavailable, clamped to at least 1 second |

If the Gemini startup check or a summary request fails, flash pushes pause and a background task checks the connection every 30 seconds until it recovers. The monitor keeps receiving news and saving matching items as context, without forwarding raw text. Skipped items are not replayed after recovery. A missing API key also pauses pushes. This recovery task operates independently of the existing Jin10 WebSocket reconnect loop. An unset or blank `GEMINI_MODEL` uses the default model.

### Q&A settings

| Variable | Default | Purpose |
|---|---|---|
| `CONTEXT_SNIPPET_LIMIT` | `40` | Number of recent items included in the answer prompt |

### YouTube monitor settings

| Variable | Default | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN_02` | empty | Telegram bot token used for YouTube summary pushes |
| `YT_CHANNELS_CONFIG` | `config/yt_channels.json` | Path to the YouTube channel configuration |
| `YT_MAX_NEW_PER_RUN` | `3` | Maximum new videos per run when a channel does not set its own limit |
| `YT_SEEN_STATE_FILE` | `data/yt_seen_ids.json` | Path to the processed-video state file |
| `YT_MAX_SEEN_IDS` | `300` | Maximum processed video IDs retained per channel |

---

## Development and testing

```bash
pip install -r requirements-dev.txt
pytest          # unit tests; never touches the network
ruff check .    # static checks
```

The suite covers Jin10 flash parsing and the binary WebSocket protocol, the outbox back-pressure behaviour, Telegram retry and throttling logic, YouTube RSS parsing and the dedup state machine, and the Q&A question detection. No API keys are required and no network requests are made.

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
