"""Durable Telegram long-polling receipt used to reduce replay after restarts."""

import json
import os
from pathlib import Path

from common import STATE_DIR

UPDATE_STATE_FILE = Path(os.getenv("TELEGRAM_UPDATE_STATE_FILE", str(STATE_DIR / "telegram_update_state.json")))


class UpdateStateError(RuntimeError):
    pass


def load_last_update_id() -> int | None:
    try:
        state = json.loads(UPDATE_STATE_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise UpdateStateError("Cannot read Telegram update receipt") from exc
    value = state.get("last_update_id") if isinstance(state, dict) else None
    if type(value) is not int or value < 0:
        raise UpdateStateError("Telegram update receipt is invalid")
    return value


def save_last_update_id(update_id: int) -> None:
    if type(update_id) is not int or update_id < 0:
        raise UpdateStateError("Telegram update ID is invalid")
    try:
        UPDATE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = UPDATE_STATE_FILE.with_suffix(".json.tmp")
        temporary.write_text(json.dumps({"last_update_id": update_id}), encoding="utf-8")
        temporary.replace(UPDATE_STATE_FILE)
    except OSError as exc:
        raise UpdateStateError("Cannot save Telegram update receipt") from exc
