"""Poll configurable RSS/Atom sources and emit normalized flash items."""

import asyncio
import hashlib
import json
import os
import re
from html import unescape
from pathlib import Path
from typing import Awaitable, Callable
from xml.etree import ElementTree

import aiohttp

from common import BASE_DIR, get_logger

FEEDS_FILE = Path(os.getenv("NEWS_FEEDS_FILE", str(BASE_DIR / "config" / "news_feeds.json")))
FEED_STATE_FILE = Path(os.getenv("FEED_STATE_FILE", str(BASE_DIR / "data" / "feed_seen.json")))
FEED_POLL_INTERVAL = max(30.0, float(os.getenv("FEED_POLL_INTERVAL", "120")))
FEED_TIMEOUT = max(1.0, float(os.getenv("FEED_TIMEOUT", "20")))
MAX_SEEN_PER_FEED = 500
log = get_logger("feeds")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(element: ElementTree.Element, *names: str) -> str:
    wanted = set(names)
    for child in element:
        if _local_name(child.tag) not in wanted:
            continue
        if _local_name(child.tag) == "link" and child.get("href"):
            return child.get("href", "").strip()
        return "".join(child.itertext()).strip()
    return ""


def _clean_markup(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(unescape(value).split())


def parse_feed(payload: bytes, source: str) -> list[dict]:
    """Parse RSS 2.0 or Atom into the item shape consumed by jin10_monitor."""
    root = ElementTree.fromstring(payload)
    entries = [node for node in root.iter() if _local_name(node.tag) in {"item", "entry"}]
    parsed = []
    for entry in entries:
        title = _clean_markup(_child_text(entry, "title"))
        content = _clean_markup(_child_text(entry, "description", "summary", "content"))
        link = _child_text(entry, "link")
        identity = _child_text(entry, "guid", "id") or link
        if not title and not content:
            continue
        if not identity:
            identity = hashlib.sha256(f"{source}\0{title}\0{content}".encode()).hexdigest()
        digest = hashlib.sha256(f"{source}\0{identity}".encode()).hexdigest()[:32]
        parsed.append({
            "id": f"feed:{digest}",
            "data": {"title": title, "content": content},
            "source": source,
            "url": link,
        })
    return parsed


def load_feeds(path: Path = FEEDS_FILE) -> list[dict]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.error("Cannot load news feeds from %s: %s", path, exc)
        return []
    feeds = []
    names = set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or item.get("enabled", True) is False:
            continue
        name = str(item.get("name") or "").strip()
        url = str(item.get("url") or "").strip()
        if not name or name in names or not url.startswith("https://"):
            log.warning("Ignoring invalid or duplicate feed entry: %r", item)
            continue
        names.add(name)
        feeds.append({"name": name, "url": url})
    return feeds


def load_state(path: Path | None = None) -> dict[str, list[str]]:
    path = path or FEED_STATE_FILE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        log.warning("Cannot load feed state; current entries will be used as a safe baseline: %s", exc)
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(name): [str(value) for value in values[:MAX_SEEN_PER_FEED]]
        for name, values in raw.items()
        if isinstance(name, str) and isinstance(values, list)
    }


def save_state(state: dict[str, list[str]], path: Path | None = None) -> None:
    path = path or FEED_STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


async def fetch_feed(session: aiohttp.ClientSession, feed: dict) -> list[dict]:
    headers = {"User-Agent": "CryptoFlash/1.0 (+personal news monitor)", "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"}
    async with session.get(feed["url"], headers=headers, timeout=aiohttp.ClientTimeout(total=FEED_TIMEOUT)) as response:
        response.raise_for_status()
        return parse_feed(await response.read(), feed["name"])


async def poll_once(
    session: aiohttp.ClientSession,
    feeds: list[dict],
    state: dict[str, list[str]],
    emit: Callable[[dict], Awaitable[None]],
) -> None:
    changed = False
    for feed in feeds:
        try:
            items = await fetch_feed(session, feed)
        except (aiohttp.ClientError, asyncio.TimeoutError, ElementTree.ParseError, UnicodeError) as exc:
            log.warning("Feed %s unavailable: %s", feed["name"], exc)
            continue
        current_ids = [item["id"] for item in items]
        if feed["name"] not in state:
            state[feed["name"]] = current_ids[:MAX_SEEN_PER_FEED]
            changed = True
            log.info("Feed %s initialized with %d existing entries; history will not be replayed", feed["name"], len(items))
            continue
        known = set(state[feed["name"]])
        new_items = [item for item in items if item["id"] not in known]
        for item in reversed(new_items):
            await emit(item)
        combined = list(dict.fromkeys(current_ids + state[feed["name"]]))[:MAX_SEEN_PER_FEED]
        if combined != state[feed["name"]]:
            state[feed["name"]] = combined
            changed = True
        if new_items:
            log.info("Feed %s emitted %d new entries", feed["name"], len(new_items))
    if changed:
        try:
            save_state(state)
        except OSError as exc:
            log.error("Cannot persist feed state; stopping RSS ingestion to prevent duplicate floods: %s", exc)
            raise


async def feed_loop(session: aiohttp.ClientSession, emit: Callable[[dict], Awaitable[None]]) -> None:
    feeds = load_feeds()
    if not feeds:
        log.warning("No valid RSS/Atom feeds configured; only Jin10 will be monitored")
        return
    state = load_state()
    while True:
        await poll_once(session, feeds, state, emit)
        await asyncio.sleep(FEED_POLL_INTERVAL)


async def check_feeds() -> int:
    """Validate configured endpoints and XML without changing seen state."""
    failures = 0
    async with aiohttp.ClientSession() as session:
        for feed in load_feeds():
            try:
                items = await fetch_feed(session, feed)
                print(f"{feed['name']}: {len(items)} entries")
            except Exception as exc:
                failures += 1
                print(f"{feed['name']}: unavailable ({type(exc).__name__}: {exc})")
    return failures


if __name__ == "__main__":
    raise SystemExit(asyncio.run(check_feeds()))
