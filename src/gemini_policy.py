"""Persist request budgets and cooldowns; one writer process per workflow scope."""

import hashlib
import json
import math
import os
import random
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from common import BASE_DIR

TAIPEI = timezone(timedelta(hours=8))
DEFAULT_LIMITS = {"youtube": 120, "live": 600}


class PolicyStateError(RuntimeError):
    pass


def state_path(scope: str) -> Path:
    if scope not in DEFAULT_LIMITS:
        raise PolicyStateError("Unknown Gemini usage scope")
    return Path(os.getenv(f"GEMINI_{scope.upper()}_USAGE_FILE") or BASE_DIR / "data" / f"gemini_{scope}_usage.json")


def daily_limit(scope: str) -> int:
    try:
        limit = int(os.getenv(f"GEMINI_{scope.upper()}_DAILY_REQUESTS") or DEFAULT_LIMITS[scope])
        if limit < -1:
            raise ValueError
        return limit
    except (ValueError, KeyError) as exc:
        raise PolicyStateError("Daily request limit must be -1 or a nonnegative integer") from exc


def read_state(scope: str) -> dict:
    path = state_path(scope)
    try:
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(state, dict):
            raise ValueError
        if state:
            for field in ("day", "config", "last_error"):
                if not isinstance(state.get(field), str):
                    raise ValueError
            datetime.strptime(state["day"], "%Y-%m-%d")
            for field in ("used", "failures"):
                if type(state.get(field)) is not int or state[field] < 0:
                    raise ValueError
            if type(state.get("blocked")) is not bool:
                raise ValueError
            if (type(state.get("retry_at")) not in (float, int)
                    or not math.isfinite(state["retry_at"]) or state["retry_at"] < 0):
                raise ValueError
            if not isinstance(state.get("rejected"), list) or any(not isinstance(x, str) for x in state["rejected"]):
                raise ValueError
        return state
    except (OSError, ValueError, TypeError) as exc:
        raise PolicyStateError("Cannot read Gemini usage state; requests paused") from exc


def write_state(scope: str, state: dict) -> None:
    path = state_path(scope)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        raise PolicyStateError("Cannot save Gemini usage state; requests paused") from exc


def reserve(scope: str, config: str, request_id: str) -> str | None:
    """Charge an attempt before network I/O, including failed/ambiguous attempts."""
    now = time.time()
    day = datetime.fromtimestamp(now, TAIPEI).date().isoformat()
    state = read_state(scope)
    if not state:
        state = {"day": day, "used": 0, "config": config, "failures": 0,
                 "retry_at": 0, "last_error": "", "blocked": False, "rejected": []}
    if state["day"] != day:
        state.update(day=day, used=0)
    if state["config"] != config:
        state.update(config=config, failures=0, retry_at=0, blocked=False, rejected=[], last_error="")
    limit = daily_limit(scope)
    reason = None
    if limit >= 0 and state["used"] >= limit:
        reason = "daily_budget"
    elif state["blocked"]:
        reason = "configuration_blocked"
    elif request_id in state["rejected"]:
        reason = "invalid_request_blocked"
    elif now < state["retry_at"]:
        reason = "cooldown"
    if not reason:
        state["used"] += 1
    write_state(scope, state)
    return reason


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def classify(status: int, data: dict, headers: dict) -> tuple[str, float]:
    """Never persist provider error bodies, which can contain input or credentials."""
    delay = 0.0
    retry_after = headers.get("Retry-After", "")
    try:
        delay = max(0.0, float(retry_after))
    except (ValueError, TypeError):
        try:
            delay = max(0.0, parsedate_to_datetime(retry_after).timestamp() - time.time())
        except (ValueError, TypeError, AttributeError):
            pass
    error = data.get("error") or {}
    if not isinstance(error, dict):
        error = {}
    details = error.get("details") or []
    reasons = {d.get("reason") for d in details if isinstance(d, dict)} if isinstance(details, list) else set()
    daily = False
    for detail in details if isinstance(details, list) else []:
        if not isinstance(detail, dict):
            continue
        if str(detail.get("@type", "")).endswith("RetryInfo"):
            try:
                delay = max(delay, float(str(detail.get("retryDelay", "0s")).removesuffix("s")))
            except ValueError:
                pass
        if str(detail.get("@type", "")).endswith("QuotaFailure"):
            daily |= "perday" in json.dumps(detail).lower() or "per_day" in json.dumps(detail).lower()
    if not math.isfinite(delay):
        delay = 0.0
    if status == 429:
        return ("daily_quota" if daily else "rate_limit"), max(delay, 86400 if daily else 0)
    if status in (401, 403) or reasons & {"API_KEY_INVALID", "API_KEY_EXPIRED", "API_KEY_SERVICE_BLOCKED"}:
        return "authentication", 0
    if status in (402, 404) or error.get("status") == "FAILED_PRECONDITION":
        return "model_configuration", 0
    if status in (408, 504):
        return "timeout", delay
    if status >= 500:
        return "provider_unavailable", delay
    return "invalid_request", 0


def failed(scope: str, category: str, request_id: str, provider_delay: float = 0) -> None:
    state = read_state(scope)
    state["last_error"] = category
    if category in ("authentication", "model_configuration"):
        state["blocked"] = True
    elif category == "invalid_request":
        state["rejected"] = (state["rejected"] + [request_id])[-100:]
    else:
        state["failures"] += 1
        delay = min(3600, 30 * 2 ** min(state["failures"] - 1, 7))
        delay = min(3600, delay * random.uniform(1.0, 1.2))
        state["retry_at"] = time.time() + max(delay, provider_delay)
    write_state(scope, state)


def succeeded(scope: str) -> None:
    state = read_state(scope)
    state.update(failures=0, retry_at=0, last_error="")
    write_state(scope, state)
