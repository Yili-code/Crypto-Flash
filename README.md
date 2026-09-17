# Crypto Flash

An automated crypto-news monitoring system that filters high-volume market updates, uses Gemini to classify and summarize relevant events, and delivers actionable context through Telegram.

[繁體中文完整文件](docs/README.md) · [Full English documentation](docs/README.en.md)

## What it demonstrates

- Resilient WebSocket ingestion with reconnect and idle-timeout handling
- A bounded processing queue that protects ingestion under back pressure
- Gemini-based relevance grading, summaries, and background recovery
- Telegram delivery with throttling and rate-limit retries
- Searchable recent news, daily digests, and topic timelines
- YouTube RSS monitoring with persistent deduplication state
- Scheduled GitHub Actions with conflict-aware state persistence
- Offline unit tests that require no API keys or network access

## System flow

```text
Jin10 WebSocket → parse → filter → bounded queue
                                  ↓
                         Gemini classify/summarize
                                  ↓
                  archive context → Telegram delivery
                         ↓
            search, digest, tracking, and Q&A
```

## Quick start

Requires Python 3.12 or newer.

```bash
git clone https://github.com/Yili-code/Crypto-Flash.git
cd Crypto-Flash
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS / Linux
# source .venv/bin/activate

python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env`, add the Telegram and Gemini values you need, then run the combined monitor and assistant:

```bash
python src/flash_service.py
```

Individual services can also run independently. See the [complete setup guide](docs/README.en.md) for workflows, commands, environment variables, state retention, and operational caveats.

## Development checks

```bash
python -m pip install -r requirements-dev.txt
ruff check .
pytest
```

The CI workflow runs the same lint and test checks without secrets. Tests cover parsing, queue back pressure, retry behavior, deduplication, Telegram commands, digests, event tracking, and Gemini recovery.

## Important

AI-generated summaries are informational and may be incomplete or incorrect. This project is for technical learning and personal monitoring; it does not provide investment advice.
