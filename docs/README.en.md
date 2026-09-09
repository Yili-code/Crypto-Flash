<div align="center">

# Crypto Flash

**News grading · On-demand queries · Daily roundups · Event tracking**

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
- News queries and freshness: `src/news_commands.py`, with `/news`, `/search`, `/important`, and `/status`
- Daily roundups: `src/daily_digest.py`, with `/digest` queries and scheduled delivery at 08:15 UTC+8
- Event tracking: `src/event_tracking.py`, with subscriptions, timelines, and unread updates
- Historical news archive: `src/news_archive.py`, shared by roundups and event tracking
- Background Gemini recovery, Telegram rate-limit retries, and a bounded news-processing queue
- Shared recent-news context: `data/recent_news.json`
- Scheduled execution via GitHub Actions: Jin10 every 6 hours and YouTube every 30 minutes

---

## How it works

```text
Jin10 WebSocket → Parse packets → Bounded queue → Keyword matching
   ↓
Gemini available: grade and summarize; unavailable: keep ungraded record
   ↓
Save recent_news.json (default: 6 hours / 80 records)
Save news_archive.json (72 hours / 5,000 records)
   ↓
Summary available, relevant, and above the push threshold → Telegram push

recent_news.json → News queries, status, and AI Q&A context
news_archive.json → Daily roundups, timelines, and tracked updates
```

`jin10_monitor.py` and `telegram_assistant.py` run as separate processes and share the same `recent_news.json` file for context.

Records are saved before the push threshold check and Telegram delivery, so a saved record does not prove delivery. The default `MEDIUM` threshold sends CRITICAL, HIGH, and MEDIUM; LOW or irrelevant items can still be retained. When the queue fills, the oldest pending item is dropped before processing and is not archived.

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

Bot 01 handles Jin10 pushes, news commands, tracking, Q&A, and daily delivery; bot 02 handles YouTube. News queries, roundups, and tracking need no Gemini key, but require saved news data. `TELEGRAM_CHAT_ID` also restricts which chat the assistant accepts. Run the commands from the project root with Python 3.12; start the monitor and assistant in separate terminals.

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

### News queries and daily roundups

| Command | Purpose |
|---|---|
| `/digest` | Yesterday's roundup, ordered by CRITICAL, HIGH, MEDIUM; up to 8 events |
| `/digest today` | Today's roundup so far |
| `/digest YYYY-MM-DD` | A selected date within the retained archive |
| `/news`, `/news 10` | Latest 5 or 10 records, with a maximum of 10 |
| `/search BTC` | Case-insensitive title/body search; multiple words match as a phrase |
| `/important`, `/important 10` | HIGH and CRITICAL news only |
| `/status` | Record counts, tier distribution, and latest record timestamp |
| `/help`, `/start` | Command guide |

These commands work without a Gemini key and accept `/command@bot_username` in groups. The assistant must be running to answer them. News queries display source excerpts; daily roundups reuse previously generated AI summaries, with no new model calls or cross-event inference. Ungraded raw news is never substituted for a daily summary.

Like the Jin10 monitor, the assistant workflow starts every six hours and runs the service for 350 minutes, leaving time to persist tracking progress before the 360-minute job deadline. This provides near-continuous availability, with a gap between runs that scheduling delays can extend; it is not seamless 24/7 operation. Daily delivery is an independent workflow and does not require the assistant to be running.

`daily_digest.yml` is scheduled for **08:15 UTC+8**, delivering the previous calendar day's roundup through bot 01. Dates use the news ingestion timestamp in UTC+8. The separate `data/news_archive.json` retains **72 hours, up to 5,000 records**; the existing six-hour Q&A context stays unchanged. First use needs time to accumulate records. Empty or partial data is identified explicitly, and observed timestamps do not imply complete coverage.

Actions read the files available at checkout; updates in a running monitor are only visible after persistence. `/status` describes that data snapshot, not live connection health. The monitor stops after 350 minutes to leave time for persistence before its job deadline.

Successful delivery records the date in `data/daily_digest_state.json`; rerunning the same day skips delivery, and failed sends do not advance state. Corrupt state stops the job. A crash or persistence failure after sending can still cause a duplicate on retry, so inspect delivery logs before rerunning a failed job.

Scheduled execution requires merging the workflow into the default branch, and GitHub schedules may be delayed. Manual workflow dispatch is also available. Running `python src/daily_digest.py` locally **sends** yesterday's report.

### Choosing a query

| Need | Command and data scope |
|---|---|
| Scan recent news | `/news`, `/search`, `/important`: default six-hour context, up to 80 stored records |
| Review a day | `/digest`: selected date within the 72-hour archive, using saved summaries |
| Review a topic | `/timeline phrase`: 72-hour archive, no subscription required |
| Resume reading | `/track phrase`, then `/updates`: unread developments collected after subscribing |
| Ask for analysis | `/ask question`: defaults to 40 recent background titles or body openings; requires Gemini |

These scopes help avoid mistaking an empty short-term search for an absence of events, while unread progress reduces repeated reading. All queries depend on collected data; `/ask` does not perform a live web search.

### Event tracking and follow-ups

| Command | Purpose |
|---|---|
| `/track spot ETF` | Track this case-insensitive phrase from the time it is added |
| `/tracks` | List topics and unread counts |
| `/timeline spot ETF` | Latest 8 matching records from the 72-hour archive, ordered by ingestion time |
| `/updates` | Read new records across tracked topics, oldest first, up to 8 at a time |
| `/updates spot ETF` | Read new records for one tracked topic |
| `/untrack spot ETF` | Remove a subscription without deleting news |

Matching uses the full phrase in titles, bodies, and saved summaries, without model calls or inferred causal links. Translations and synonyms are not expanded automatically. Timeline queries do not require a subscription or change reading progress. Output distinguishes saved summary excerpts from source excerpts.

Updates are on demand, not additional automatic alerts. Reading progress advances only after Telegram confirms delivery, and only for displayed records. Overflow stays unread for the next request. A record matching multiple topics is shown once in a combined query; a topic-specific query advances only that topic. Existing records remain available through `/timeline`, but are not unread when a new subscription is created. Re-adding a phrase does not reset progress.

Up to 12 topics of 40 characters each are supported. The configured `TELEGRAM_CHAT_ID` shares one topic list and progress state: members who can issue commands can manage it. Event commands are disabled without a configured chat. The assistant is the sole writer of `data/event_tracking.json` and commits it after each workflow run, so topic visibility follows repository visibility. Local installations may set `EVENT_STATE_FILE` to another path.

The 72-hour/5,000-record archive and checkout snapshot still limit coverage. Old unread records can expire, and no new records does not prove there were no external developments. If a message arrives but state writing or persistence fails, a subsequent query can repeat it.

### 6. Run the YouTube monitor (optional)

```bash
python src/yt_monitor.py
```

Before running it, add the channels to `config/yt_channels.json`. The script processes all configured channels once and then exits, so it is intended to be used with a scheduler or GitHub Actions.

---

## GitHub Actions deployment

This project includes five workflows:

| Workflow | Purpose |
|---|---|
| `flash_monitor.yml` | Runs `src/jin10_monitor.py` on a schedule and pushes filtered news |
| `telegram_assistant.yml` | Runs `src/telegram_assistant.py` to answer Telegram questions |
| `yt_monitor.yml` | Runs `src/yt_monitor.py` to monitor YouTube videos and push summaries |
| `ci.yml` | Runs `ruff` and `pytest` on push / PR; uses no secrets |
| `daily_digest.yml` | Sends yesterday's roundup at 08:15 UTC+8 and persists the delivery date |

Set these in GitHub `Settings → Secrets and variables → Actions`:

| Secret / Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Gemini API key |
| `TELEGRAM_BOT_TOKEN_01` | Telegram bot token |
| `TELEGRAM_BOT_TOKEN_02` | Telegram bot token used by the YouTube monitor |
| `TELEGRAM_CHAT_ID` | Target chat ID for pushes |
| `GEMINI_MODEL` | Optional; defaults to `gemini-3.5-flash-lite` |

The Jin10 monitor workflow runs every 6 hours. `yt_monitor.yml` runs at minute 0 and minute 30 of every hour. Both workflows support manual `workflow_dispatch`.

Set `GEMINI_MODEL` as an Actions **Variable** and the other listed credentials/chat settings as **Secrets**. To use other environment options in Actions, add them to the relevant workflow step’s `env`; creating a repository variable alone does not pass it to the script.

### State persistence

`data/recent_news.json` (recent flash-news context) and `data/yt_seen_ids.json` (already-pushed videos) have to survive between runs. Without them, the Q&A bot loses its context and the YouTube monitor warms up again, skipping the videos currently in the feed.

These files, along with `data/news_archive.json`, `data/daily_digest_state.json`, and `data/event_tracking.json`, are **committed back to the repository** by `.github/actions/persist-state` at the end of each run:

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
| `NEWS_ARCHIVE_FILE` | `data/news_archive.json` | Daily report archive, retaining 72 hours and up to 5,000 records |
| `DIGEST_STATE_FILE` | `data/daily_digest_state.json` | Most recently delivered digest date, written by the digest script |

If the Gemini startup check or a summary request fails, flash pushes pause and a background task checks the connection every 30 seconds until it recovers. The monitor keeps receiving news and saving matching items as context, without forwarding raw text. Skipped items are not replayed after recovery. A missing API key also pauses pushes. This recovery task operates independently of the existing Jin10 WebSocket reconnect loop. An unset or blank `GEMINI_MODEL` uses the default model.

### Q&A settings

| Variable | Default | Purpose |
|---|---|---|
| `CONTEXT_SNIPPET_LIMIT` | `40` | Number of recent items included in the answer prompt |
| `EVENT_STATE_FILE` | `data/event_tracking.json` | Shared topic subscriptions and acknowledged reading progress |

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

The suite covers Jin10 flash parsing and the binary WebSocket protocol, the outbox back-pressure behaviour, Telegram retry and throttling logic, YouTube RSS parsing and the dedup state machine, and Q&A question detection. It also covers news queries, digest dates and summary deduplication, digest delivery state, event unread progress and delivery acknowledgment, and Gemini recovery. No API keys are required and no network requests are made.

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
