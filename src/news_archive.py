"""A separate rolling archive for daily reports, owned by the flash monitor."""

import json
import math
import os
import time
from pathlib import Path

from common import BASE_DIR, get_logger

ARCHIVE_FILE = Path(os.getenv("NEWS_ARCHIVE_FILE", str(BASE_DIR / "data" / "news_archive.json")))
ARCHIVE_MAX_AGE_SEC = 72 * 3600
ARCHIVE_MAX_ITEMS = 5000
log = get_logger("news-archive")


def load_archive() -> list[dict]:
    try:
        items = json.loads(ARCHIVE_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        log.warning("Cannot read news archive: %s", exc)
        return []
    if not isinstance(items, list):
        return []
    now = time.time()
    valid = []
    for item in items:
        if not isinstance(item, dict):
            continue
        ts = item.get("ts")
        if isinstance(ts, bool) or not isinstance(ts, (int, float)) or not math.isfinite(ts):
            continue
        if 0 <= now - ts <= ARCHIVE_MAX_AGE_SEC:
            valid.append(item)
    return sorted(valid, key=lambda item: item["ts"])[-ARCHIVE_MAX_ITEMS:]


def archive_news(item: dict) -> None:
    items = load_archive()
    if item.get("id"):
        items = [previous for previous in items if previous.get("id") != item["id"]]
    items.append(item)
    try:
        ARCHIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = ARCHIVE_FILE.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(items[-ARCHIVE_MAX_ITEMS:], ensure_ascii=False), encoding="utf-8")
        temporary.replace(ARCHIVE_FILE)
    except OSError as exc:
        log.warning("Cannot save news archive: %s", exc)
