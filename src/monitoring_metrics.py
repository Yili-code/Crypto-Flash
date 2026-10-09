"""Durable daily operational metrics for the live flash pipeline."""

import json
import math
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from common import STATE_DIR, TIER_LEVELS, get_logger

METRICS_FILE = Path(os.getenv("MONITORING_METRICS_FILE", str(STATE_DIR / "monitoring_daily.json")))
RETENTION_DAYS = max(1, int(os.getenv("MONITORING_RETENTION_DAYS", "35")))
FLUSH_INTERVAL_SECONDS = max(1.0, float(os.getenv("MONITORING_FLUSH_INTERVAL", "30")))
TAIPEI = timezone(timedelta(hours=8))
RECEIVED_AT_KEY = "_metrics_received_at"
log = get_logger("monitoring")


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    interpolated = ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return round(interpolated)


class DailyMetrics:
    def __init__(
        self,
        path: Path = METRICS_FILE,
        retention_days: int = RETENTION_DAYS,
        flush_interval_seconds: float = FLUSH_INTERVAL_SECONDS,
    ):
        self.path = path
        self.retention_days = retention_days
        self.flush_interval_seconds = flush_interval_seconds
        self._document: dict | None = None
        self._disabled = False
        self._dirty = False
        self._last_flush = time.monotonic()

    def _load(self) -> dict:
        if self._document is not None:
            return self._document
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raw = {}
        except (OSError, ValueError) as exc:
            self._disabled = True
            log.error("Cannot read monitoring metrics; recording is disabled to preserve the file: %s", exc)
            raw = {}
        days = raw.get("days") if isinstance(raw, dict) else None
        self._document = {
            "schema_version": 1,
            "timezone": "Asia/Taipei",
            "days": days if isinstance(days, dict) else {},
        }
        return self._document

    def _day(self) -> dict:
        document = self._load()
        date = datetime.now(TAIPEI).date().isoformat()
        day = document["days"].setdefault(date, {})
        day.setdefault("received_events", 0)
        day.setdefault("keyword_filter_passed", 0)
        day.setdefault("pushes", {"total": 0, "importance": {tier: 0 for tier in TIER_LEVELS}})
        day.setdefault("duplicates_blocked", 0)
        day.setdefault("gemini_failures", 0)
        day.setdefault("telegram_delivery_failures", 0)
        day.setdefault("latency_ms", {"sample_count": 0, "p50": None, "p95": None})
        day.setdefault("latency_samples_ms", [])
        day.setdefault("queue_high_water_mark", 0)
        day.setdefault("queue_dropped_total", 0)
        return day

    def _save(self, *, force: bool = False) -> None:
        if self._disabled:
            return
        self._dirty = True
        now = time.monotonic()
        if not force and now - self._last_flush < self.flush_interval_seconds:
            return
        document = self._load()
        dates = sorted(document["days"])
        for date in dates[:-self.retention_days]:
            del document["days"][date]
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self.path)
            self._dirty = False
            self._last_flush = now
        except OSError as exc:
            log.error("Cannot persist monitoring metrics: %s", exc)

    def flush(self) -> None:
        if self._dirty:
            self._save(force=True)

    def increment(self, field: str, amount: int = 1) -> None:
        if self._disabled:
            return
        day = self._day()
        day[field] += amount
        self._save()

    def observe_received(self, item: dict) -> None:
        self.observe_batch([item])

    def observe_batch(self, items: list[dict], *, duplicates: int = 0) -> None:
        if self._disabled:
            return
        observed = 0
        received_at = time.time()
        for item in items:
            if RECEIVED_AT_KEY in item:
                continue
            item[RECEIVED_AT_KEY] = received_at
            observed += 1
        if not observed and not duplicates:
            return
        day = self._day()
        day["received_events"] += observed
        day["duplicates_blocked"] += duplicates
        self._save()

    def observe_queue_size(self, size: int) -> None:
        if self._disabled:
            return
        day = self._day()
        if size > day["queue_high_water_mark"]:
            day["queue_high_water_mark"] = size
            self._save()

    def record_push(self, tier: str | None, received_at: object) -> None:
        if self._disabled:
            return
        day = self._day()
        importance = tier if tier in TIER_LEVELS else "UNCLASSIFIED"
        day["pushes"]["total"] += 1
        day["pushes"]["importance"].setdefault(importance, 0)
        day["pushes"]["importance"][importance] += 1
        if isinstance(received_at, (int, float)):
            latency_ms = max(0, round((time.time() - received_at) * 1000))
            samples = day["latency_samples_ms"]
            samples.append(latency_ms)
            day["latency_ms"] = {
                "sample_count": len(samples),
                "p50": _percentile(samples, 0.50),
                "p95": _percentile(samples, 0.95),
            }
        self._save()


metrics = DailyMetrics()
