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
EVENT_LABELS = {
    "CPI m/m": "CPI",
    "CPI y/y": "CPI",
    "Core CPI m/m": "CPI",
    "Core CPI y/y": "CPI",
    "Non-Farm Employment Change": "非農就業",
    "Federal Funds Rate": "FOMC 利率決議",
    "FOMC Statement": "FOMC 利率決議",
    "FOMC Economic Projections": "FOMC 經濟預測",
    "FOMC Press Conference": "FOMC 記者會",
}
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
        label = EVENT_LABELS.get(row["title"].strip())
        if (row["country"] == "USD" and label
                and day <= when.astimezone(TAIPEI).date() < day + timedelta(days=WINDOW_DAYS)):
            events.add((when.astimezone(timezone.utc), label))
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
    end_label = last_day.strftime("%m/%d" if day.year == last_day.year else "%Y/%m/%d")
    header = '<b><a href="https://www.forexfactory.com/calendar">CPI · 非農 · FOMC</a></b>\n'
    header += f"{day:%Y/%m/%d}–{end_label} · 台灣時間\n"
    footer = ''
    if not events:
        return [header + "\n這三天沒有 CPI、非農或 FOMC。"]
    messages = []
    body = header
    for when, title in events:
        row = f"\n{when.astimezone(TAIPEI):%m/%d %H:%M}  {escape(title)}"
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
            notice = (f"<b>CPI · 非農 · FOMC</b>\n{day:%Y/%m/%d}–{last_day:%Y/%m/%d} · 台灣時間\n\n"
                      "資料不完整或暫時無法取得。\n不能判定是否有事件。")
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
