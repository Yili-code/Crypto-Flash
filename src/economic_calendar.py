"""Independent daily macro calendar notification; no model or news-state writes."""

import argparse
import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from html import escape

import aiohttp

from common import BASE_DIR, get_logger
from tg import TELEGRAM_CHAT_ID, send_telegram_message

TAIPEI = timezone(timedelta(hours=8))
WINDOW_DAYS = 3
CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
STATE_FILE = BASE_DIR / "data" / "economic_calendar_state.json"
log = get_logger("economic-calendar")


def select_events(payload: object, day: date) -> list[tuple[datetime, str]]:
    # Empty/stale/malformed feeds must never be interpreted as a quiet day.
    if not isinstance(payload, list) or not payload:
        raise ValueError("Calendar feed is empty or invalid")
    events = set()
    weeks = set()
    for row in payload:
        if not isinstance(row, dict) or not all(
            isinstance(row.get(key), str) and row[key].strip()
            for key in ("title", "country", "impact", "date")
        ):
            raise ValueError("Calendar entry is incomplete")
        when = datetime.fromisoformat(row["date"])
        if when.utcoffset() is None:
            raise ValueError("Calendar timestamp has no timezone")
        source_day = when.date()
        weeks.add(source_day - timedelta(days=(source_day.weekday() + 1) % 7))
        if (row["country"] == "USD" and row["impact"] == "High"
                and day <= when.astimezone(TAIPEI).date() < day + timedelta(days=WINDOW_DAYS)):
            events.add((when.astimezone(timezone.utc), row["title"].strip()))
    if len(weeks) != 1:
        raise ValueError("Calendar feed spans unexpected weeks")
    week_start = next(iter(weeks))
    # Refuse to declare no events unless the feed covers the full Taiwan window.
    source_tz = datetime.fromisoformat(payload[0]["date"]).tzinfo
    start = datetime.combine(day, datetime.min.time(), TAIPEI).astimezone(source_tz).date()
    end = (datetime.combine(day + timedelta(days=WINDOW_DAYS), datetime.min.time(), TAIPEI)
           - timedelta(microseconds=1)).astimezone(source_tz).date()
    if not (week_start <= start <= end < week_start + timedelta(days=7)):
        raise ValueError("Calendar feed does not cover the entire three-day Taiwan window")
    return sorted(events)


def render_messages(events: list[tuple[datetime, str]], day: date) -> list[str]:
    last_day = day + timedelta(days=WINDOW_DAYS - 1)
    header = f"<b>未來三天高影響數據／事件｜{day.isoformat()}～{last_day.isoformat()}</b>\n"
    header += "範圍：美元 High impact（含 Fed 政策事件）\n以台灣時間今天、明天、後天為準，含今日已發布事件。\n"
    footer = '\n來源：<a href="https://www.forexfactory.com/calendar">Forex Factory</a>；時間可能調整。'
    if not events:
        return [header + "\n這三天暫無符合上述範圍的已排定重要事件。\n仍可能有突發消息；無排定事件不代表市場不會波動。\n" + footer]
    messages = []
    body = header
    for when, title in events:
        row = (f"\n<b>{escape(title)}</b>\n"
               f"國際時間 UTC：{when:%Y-%m-%d %H:%M}\n"
               f"台灣時間 UTC+8：{when.astimezone(TAIPEI):%Y-%m-%d %H:%M}\n")
        if len((header + row + footer).encode("utf-16-le")) // 2 > 4000:
            raise ValueError("Calendar title exceeds message limit")
        if len((body + row + footer).encode("utf-16-le")) // 2 > 4000:
            messages.append(body + footer)
            body = header
        body += row
    return messages + [body + footer]


async def fetch_calendar(session: aiohttp.ClientSession) -> object:
    async with session.get(
        CALENDAR_URL, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        timeout=aiohttp.ClientTimeout(total=30),
    ) as response:
        response.raise_for_status()
        return await response.json(content_type=None)


async def main(*, dry_run: bool = False) -> None:
    day = datetime.now(TAIPEI).date()
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError("Invalid delivery state")
    except FileNotFoundError:
        state = {}
    if not dry_run and state.get("last_sent_date") == day.isoformat():
        return
    async with aiohttp.ClientSession() as session:
        try:
            messages = render_messages(select_events(await fetch_calendar(session), day), day)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError) as exc:
            last_day = day + timedelta(days=WINDOW_DAYS - 1)
            notice = (f"未來三天高影響數據通知｜{day.isoformat()}～{last_day.isoformat()}\n"
                      "資料暫時無法確認或未涵蓋完整三天（可能跨週），不能判定這三天是否有高影響數據。")
            if dry_run:
                print(notice)
            else:
                await send_telegram_message(session, TELEGRAM_CHAT_ID, notice)
            raise RuntimeError("Calendar unavailable; delivery state was not advanced") from exc
        if dry_run:
            print("\n\n".join(messages))
            return
        for message in messages:
            if not await send_telegram_message(session, TELEGRAM_CHAT_ID, message):
                raise RuntimeError("Calendar delivery failed; delivery state was not advanced")
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps({"last_sent_date": day.isoformat()}), encoding="utf-8")
    temporary.replace(STATE_FILE)
    log.info("Calendar notification delivered for %s", day)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print without sending or saving state")
    asyncio.run(main(dry_run=parser.parse_args().dry_run))
