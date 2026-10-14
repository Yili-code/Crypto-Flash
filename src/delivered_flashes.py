"""Successful flash deliveries, owned exclusively by the live service."""

import json
import time

from common import STATE_DIR

STATE_FILE = STATE_DIR / "delivered_flashes.json"


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def load_deliveries():
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"since": time.time(), "items": []}
    if data == {}:
        return {"since": time.time(), "items": []}
    if (not isinstance(data, dict) or not isinstance(data.get("since"), (int, float))
            or not isinstance(data.get("items"), list)):
        raise ValueError("Invalid flash delivery journal")
    for item in data["items"]:
        if (not isinstance(item, dict) or not isinstance(item.get("sent_at"), (int, float))
                or not isinstance(item.get("summary"), str)):
            raise ValueError("Invalid flash delivery record")
    return data


def initialize():
    save_json(STATE_FILE, load_deliveries())


def record_delivery(summary, *, source, url):
    now = time.time()
    data = load_deliveries()
    data["items"] = [item for item in data["items"] if item["sent_at"] >= now - 72 * 3600]
    data["items"].append({"sent_at": now, "summary": summary, "source": source, "url": url})
    save_json(STATE_FILE, data)
