# Crypto Flash output demo

This page shows output produced by the project. It is not a hosted bot or a claim about prediction accuracy.

## Ranked market alert

![Telegram alert containing a ranked macro news summary and crypto impact](../assets/demo001.png)

The alert demonstrates the visible result of the main pipeline: a matching market event is classified, summarized, and delivered with macro and crypto context.

What this image does **not** prove: continuous uptime, source completeness, factual accuracy, delivery latency, or trading performance. Those depend on upstream sources, Gemini, Telegram, runner availability, and the user's configuration.

## Daily digest

![Telegram daily digest summarizing important macro and liquidity developments](../assets/daily-digest.png)

The scheduled digest compresses retained `CRITICAL` and `HIGH` events into a short briefing. A successful screenshot does not prove that every scheduled run will start on time or that upstream sources were complete.

## Query and tracking interface

![Telegram command menu for search, digests, topic tracking, and Gemini analysis](../assets/command-menu.png)

The assistant can answer a Telegram question using recently monitored items as background. It does not search the live web during `/ask`, and its answer may be incomplete or incorrect.

## Reproduce the experience

After completing the [Quick start](../README.md#quick-start), run:

```bash
python src/flash_service.py
```

Then use one of these Telegram interactions:

```text
/news
/important
/digest today
/search BTC
/ask Explain how this event could affect crypto liquidity
```

Results depend on the news retained by your own instance. Query commands use saved data; `/ask` additionally requires Gemini.

## What to capture for a useful bug report

When output differs from the documented behavior, include the command or source type, the commit SHA, Python version, local or GitHub Actions environment, and redacted logs. Never include bot tokens, chat IDs, private messages, or production state.
