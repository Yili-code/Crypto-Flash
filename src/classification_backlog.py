"""Durable, bounded retry state for flash items awaiting Gemini classification."""

import hashlib
import json
import os
import time
from pathlib import Path

from common import STATE_DIR, get_logger

BACKLOG_FILE = Path(os.getenv("CLASSIFICATION_BACKLOG_FILE", str(STATE_DIR / "classification_backlog.json")))
MAX_ITEMS = max(1, int(os.getenv("CLASSIFICATION_BACKLOG_MAX_ITEMS", "500")))
MAX_AGE_SECONDS = max(60, int(os.getenv("CLASSIFICATION_BACKLOG_MAX_AGE_SEC", "3600")))
log = get_logger("classification-backlog")


class BacklogStateError(RuntimeError):
    """Refuse to overwrite backlog state that cannot be read safely."""


def item_identity(item: dict) -> str:
    explicit = str(item.get("id") or "").strip()
    if explicit:
        return explicit
    encoded = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
    return "derived:" + hashlib.sha256(encoded.encode()).hexdigest()[:32]


def load(now: float | None = None) -> list[dict]:
    now = time.time() if now is None else now
    try:
        raw = json.loads(BACKLOG_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        raise BacklogStateError("Cannot read classification backlog; retry processing is paused") from exc
    if not isinstance(raw, list):
        raise BacklogStateError("Classification backlog must be a list")
    valid = []
    for record in raw:
        if not isinstance(record, dict) or not isinstance(record.get("item"), dict):
            raise BacklogStateError("Classification backlog contains an invalid record")
        if not isinstance(record.get("id"), str) or not isinstance(record.get("queued_at"), (int, float)):
            raise BacklogStateError("Classification backlog contains invalid metadata")
        if type(record.get("attempts")) is not int or record["attempts"] < 0:
            raise BacklogStateError("Classification backlog contains an invalid attempt count")
        if now - record["queued_at"] <= MAX_AGE_SECONDS:
            valid.append(record)
    return valid[-MAX_ITEMS:]


def save(records: list[dict]) -> None:
    try:
        BACKLOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = BACKLOG_FILE.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(records[-MAX_ITEMS:], ensure_ascii=False), encoding="utf-8")
        temporary.replace(BACKLOG_FILE)
    except OSError as exc:
        raise BacklogStateError("Cannot save classification backlog") from exc


def enqueue(item: dict, now: float | None = None) -> None:
    now = time.time() if now is None else now
    records = load(now)
    identifier = item_identity(item)
    existing = next((record for record in records if record["id"] == identifier), None)
    if existing:
        existing["attempts"] += 1
        existing["last_attempt_at"] = now
        existing["item"] = item
    else:
        records.append({
            "id": identifier,
            "queued_at": now,
            "last_attempt_at": now,
            "attempts": 1,
            "item": item,
        })
    save(records)


def remove(identifier: str) -> None:
    records = load()
    remaining = [record for record in records if record["id"] != identifier]
    if len(remaining) != len(records):
        save(remaining)


def pending(limit: int = 25) -> list[dict]:
    records = load()
    return sorted(records, key=lambda record: (record["queued_at"], record["id"]))[:max(0, limit)]
