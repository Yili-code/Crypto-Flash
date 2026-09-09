"""Daily event roundup built from saved Gemini summaries, without new model calls."""

import asyncio
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from html import escape, unescape
from pathlib import Path

import aiohttp

from common import BASE_DIR, TIER_RANK, get_logger
from news_archive import load_archive
from tg import TELEGRAM_CHAT_ID, send_telegram_message

DISPLAY_TZ = timezone(timedelta(hours=8))
DIGEST_STATE_FILE = Path(os.getenv("DIGEST_STATE_FILE", str(BASE_DIR / "data" / "daily_digest_state.json")))
log = get_logger("daily-digest")


def previous_day() -> date:
    return datetime.now(DISPLAY_TZ).date() - timedelta(days=1)


def build_digest(day: date) -> str:
    start = datetime.combine(day, datetime.min.time(), DISPLAY_TZ).timestamp()
    end = start + 86400
    items = [item for item in load_archive() if start <= item["ts"] < end]
    heading = f"<b>每日重點｜{day.isoformat()}</b>\n00:00–24:00 UTC+8（按收錄時間）\n"
    if not items:
        return heading + "\n沒有可用的新聞紀錄。可能尚未累積資料或監控中斷，並不代表當天沒有重要事件。"
    candidates = [
        item for item in items
        if item.get("tier") in ("CRITICAL", "HIGH", "MEDIUM")
        and item.get("relevant") is not False
        and isinstance(item.get("summary"), str) and item["summary"].strip()
    ]
    candidates.sort(key=lambda item: (TIER_RANK[item["tier"]], -item["ts"]))
    important = sum(item.get("tier") in ("CRITICAL", "HIGH") for item in candidates)
    ungraded = sum(item.get("tier") not in tuple(TIER_RANK) for item in items)
    rows = []
    used = set()
    for item in candidates:
        plain = " ".join(unescape(re.sub(r"<[^>]*>", "", item["summary"])).split())
        if not plain or plain in used:
            continue
        used.add(plain)
        excerpt = plain if len(plain) <= 220 else plain[:219] + "…"
        clock = datetime.fromtimestamp(item["ts"], DISPLAY_TZ).strftime("%H:%M")
        row = f"<b>{item['tier']} · {clock}</b>\n{escape(excerpt)}"
        if sum(len(part.encode("utf-16-le")) // 2 for part in rows + [row]) > 2800:
            break
        rows.append(row)
        if len(rows) == 8:
            break
    first = datetime.fromtimestamp(min(item["ts"] for item in items), DISPLAY_TZ).strftime("%H:%M")
    last = datetime.fromtimestamp(max(item["ts"] for item in items), DISPLAY_TZ).strftime("%H:%M")
    overview = f"紀錄 {len(items)} 則 · HIGH/CRITICAL {important} 則 · 未分級 {ungraded} 則\n"
    body = "\n\n".join(rows) if rows else "沒有可列出的已摘要重要快訊；未分級原文不會自動轉送。"
    return (
        heading + overview + f"\n<b>重要事件（按等級排序，列出 {len(rows)} 則）</b>\n" + body
        + f"\n\n資料紀錄：{first}–{last} UTC+8，僅代表已收錄時間，不保證全天完整。"
        + "\n使用既有 AI 摘要節錄，不新增推論；指定日期可用 /digest YYYY-MM-DD 查詢。"
    )


async def main() -> None:
    day = previous_day()
    try:
        state = json.loads(DIGEST_STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError("digest state must be an object")
    except FileNotFoundError:
        state = {}
    except (OSError, ValueError) as exc:
        raise RuntimeError("Cannot read digest delivery state; refusing to risk a duplicate send") from exc
    if state.get("last_sent_date") == day.isoformat():
        log.info("Daily digest for %s was already sent", day)
        return
    async with aiohttp.ClientSession() as session:
        if not await send_telegram_message(session, TELEGRAM_CHAT_ID, build_digest(day)):
            raise RuntimeError("Daily digest delivery failed; delivery state was not advanced")
    DIGEST_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = DIGEST_STATE_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps({"last_sent_date": day.isoformat(), "sent_at": time.time()}), encoding="utf-8")
    temporary.replace(DIGEST_STATE_FILE)


if __name__ == "__main__":
    asyncio.run(main())
