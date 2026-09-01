import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv

# ─── Path ───────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


_log = get_logger("common")

# ─── Tier Levels ────────────────────────────────────────────────────────────

TIER_LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
TIER_RANK = {level: rank for rank, level in enumerate(TIER_LEVELS, start=1)}


def resolve_max_tier(raw: str) -> int:
    raw = raw.strip().upper()
    if raw in TIER_RANK:
        return TIER_RANK[raw]
    try:
        return int(raw)
    except ValueError:
        return TIER_RANK["MEDIUM"]


MAX_TIER_TO_SEND = resolve_max_tier(os.getenv("MAX_TIER_TO_SEND", "MEDIUM"))

# ─── Recent News Context (written by monitor, read by qa; shared access logic to prevent format drift) ──

NEWS_CONTEXT_FILE = Path(os.getenv("NEWS_CONTEXT_FILE", str(BASE_DIR / "data" / "recent_news.json")))
CONTEXT_MAX_ITEMS = int(os.getenv("CONTEXT_MAX_ITEMS", "80"))
CONTEXT_MAX_AGE_SEC = int(os.getenv("CONTEXT_MAX_AGE_SEC", str(6 * 3600)))


def load_recent_news() -> list[dict]:
    if not NEWS_CONTEXT_FILE.exists():
        return []
    try:
        items = json.loads(NEWS_CONTEXT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _log.warning("Failed to load recent news context file: %s", exc)
        return []
    if not isinstance(items, list):
        return []
    now = time.time()
    return [it for it in items if isinstance(it, dict) and now - it.get("ts", 0) <= CONTEXT_MAX_AGE_SEC]


def save_recent_news(items: list[dict]) -> None:
    try:
        NEWS_CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = NEWS_CONTEXT_FILE.with_suffix(NEWS_CONTEXT_FILE.suffix + ".tmp")
        tmp_path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(NEWS_CONTEXT_FILE)
    except OSError as exc:
        _log.warning("Failed to write recent news context file: %s", exc)