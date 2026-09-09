"""Shared keyword subscriptions and acknowledged progress over the news archive."""

import hashlib
import json
import math
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from html import escape, unescape
from pathlib import Path

from common import BASE_DIR, TIER_LEVELS
from daily_digest import DISPLAY_TZ
from news_archive import load_archive

EVENT_STATE_FILE = Path(os.getenv("EVENT_STATE_FILE", str(BASE_DIR / "data" / "event_tracking.json")))
EVENT_COMMANDS = {"track", "untrack", "tracks", "timeline", "updates"}
MAX_TOPICS = 12
MAX_KEYWORD_LENGTH = 40
MAX_EVENTS = 8


class EventStateError(Exception):
    pass


@dataclass
class EventReply:
    text: str
    # topic key -> (subscription creation time, last displayed event cursor)
    progress: dict[str, tuple[float, tuple[float, str]]] = field(default_factory=dict)


def _phrase(text: str) -> str:
    return " ".join(text.split())


def _valid_time(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def load_topics() -> list[dict]:
    try:
        data = json.loads(EVENT_STATE_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        raise EventStateError("追蹤設定無法讀取，請檢查狀態檔；未覆寫既有設定。") from exc
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("topics"), list):
        raise EventStateError("追蹤設定格式不正確，請檢查狀態檔；未覆寫既有設定。")
    topics = data["topics"]
    keys = set()
    for topic in topics:
        if not isinstance(topic, dict):
            raise EventStateError("追蹤設定中的主題格式不正確。")
        keyword, created, cursor = topic.get("keyword"), topic.get("created_at"), topic.get("cursor")
        if (not isinstance(keyword, str) or not 1 <= len(keyword) <= MAX_KEYWORD_LENGTH
                or _phrase(keyword) != keyword or not keyword.isprintable()
                or keyword.casefold() in keys or not _valid_time(created)
                or not isinstance(cursor, list) or len(cursor) != 2
                or not _valid_time(cursor[0]) or not isinstance(cursor[1], str)):
            raise EventStateError("追蹤設定中的主題或閱讀進度不正確。")
        keys.add(keyword.casefold())
    if len(topics) > MAX_TOPICS:
        raise EventStateError("追蹤設定超出主題數量上限。")
    return topics


def _save_topics(topics: list[dict]) -> None:
    try:
        EVENT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = EVENT_STATE_FILE.with_suffix(".json.tmp")
        temporary.write_text(json.dumps({"version": 1, "topics": topics}, ensure_ascii=False), encoding="utf-8")
        temporary.replace(EVENT_STATE_FILE)
    except OSError as exc:
        raise EventStateError("追蹤設定未能保存，請稍後重試。") from exc


def _plain(value: object) -> str:
    return _phrase(unescape(re.sub(r"<[^>]*>", "", str(value or ""))))


def _records() -> list[dict]:
    records = {}
    for item in load_archive():
        title, content, summary = (_plain(item.get(key)) for key in ("title", "content", "summary"))
        if not (title or content or summary):
            continue
        identity = str(item.get("id") or f"{title}\n{content}\n{summary}")
        cursor = (item["ts"], hashlib.sha256(identity.encode("utf-8")).hexdigest())
        records[cursor] = {**item, "title": title, "content": content, "summary": summary,
                           "cursor": cursor, "search": f"{title} {content} {summary}".casefold()}
    return sorted(records.values(), key=lambda item: item["cursor"])


def _matches(item: dict, keyword: str) -> bool:
    return keyword.casefold() in item["search"]


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _row(item: dict, topics: list[str] | None = None) -> str:
    stamp = datetime.fromtimestamp(item["ts"], DISPLAY_TZ).strftime("%m/%d %H:%M")
    tier = item.get("tier") if item.get("tier") in TIER_LEVELS else "未分級"
    is_summary = bool(item["summary"])
    text = item["summary"] or " · ".join(part for part in (item["title"], item["content"]) if part)
    row = f"<b>{stamp} · {tier}</b> · {'摘要節錄' if is_summary else '來源摘錄'}\n{escape(_clip(text, 200))}"
    if topics:
        labels = "、".join(topics[:2]) + (f" 等 {len(topics)} 個主題" if len(topics) > 2 else "")
        row += "\n追蹤：" + escape(labels)
    return row


def _fits(rows: list[str], row: str) -> bool:
    return sum(len(part.encode("utf-16-le")) // 2 for part in rows + [row]) <= 2800


def _updates(topics: list[dict], records: list[dict], keyword: str = "") -> EventReply:
    pending = []
    for item in records:
        matches = [topic for topic in topics if item["cursor"] > tuple(topic["cursor"])
                   and _matches(item, topic["keyword"])]
        if matches:
            pending.append((item, matches))
    if not pending:
        return EventReply("<b>追蹤進展</b>\n目前保存的 72 小時資料中，沒有尚未讀取的新紀錄。\n可用 /timeline 關鍵字回顧；資料未同步或已過期的進展無法在此確認。")
    rows, progress = [], {}
    for item, matches in pending[:MAX_EVENTS]:
        row = _row(item, [topic["keyword"] for topic in matches])
        if not _fits(rows, row):
            break
        rows.append(row)
        for topic in matches:
            progress[topic["keyword"].casefold()] = (topic["created_at"], item["cursor"])
    remaining = len(pending) - len(rows)
    command = "/updates" + (f" {escape(keyword)}" if keyword else "")
    footer = f"\n\n還有 {remaining} 則，使用 {command} 繼續讀取。" if remaining else ""
    return EventReply(
        f"<b>追蹤進展</b>\n新增 {len(pending)} 則，本次顯示 {len(rows)} 則 · UTC+8 · 按收錄時間由舊到新\n\n"
        + "\n\n".join(rows) + footer, progress,
    )


def acknowledge_updates(reply: EventReply) -> None:
    """Only advance displayed topics after Telegram confirms successful delivery."""
    if not reply.progress:
        return
    topics = load_topics()
    for topic in topics:
        update = reply.progress.get(topic["keyword"].casefold())
        if update and topic["created_at"] == update[0] and update[1] > tuple(topic["cursor"]):
            topic["cursor"] = list(update[1])
    _save_topics(topics)


def event_command_reply(name: str, args: str) -> EventReply:
    args = _phrase(args)
    if name in {"track", "untrack", "timeline"} and not args:
        return EventReply(f"用法：/{name} 關鍵字，例如 /{name} spot ETF。")
    if args and (len(args) > MAX_KEYWORD_LENGTH or not args.isprintable()):
        return EventReply(f"關鍵字請使用 1–{MAX_KEYWORD_LENGTH} 個可列印字元。")
    if name == "tracks" and args:
        return EventReply("用法：/tracks（不需要參數）。")
    if name == "timeline":
        matched = [item for item in _records() if _matches(item, args)]
        rows = []
        # Select the latest events but display them chronologically.
        for item in reversed(matched[-MAX_EVENTS:]):
            row = _row(item)
            if not _fits(rows, row):
                break
            rows.insert(0, row)
        body = "\n\n".join(rows) or "沒有符合的保存紀錄。"
        return EventReply(f"<b>事件時間線：{escape(args)}</b>\n最近 72 小時 · UTC+8 · 關鍵字比對\n"
                          f"顯示最新 {len(rows)} / {len(matched)} 則，按收錄時間排序\n\n" + body)
    topics = load_topics()
    selected = next((topic for topic in topics if topic["keyword"].casefold() == args.casefold()), None)
    if name == "track":
        if selected:
            return EventReply(f"已在追蹤：{escape(selected['keyword'])}。閱讀進度不變。")
        if len(topics) >= MAX_TOPICS:
            return EventReply(f"最多追蹤 {MAX_TOPICS} 個主題，請先用 /untrack 關鍵字移除不需要的主題。")
        now = time.time()
        topics.append({"keyword": args, "created_at": now, "cursor": [now, ""]})
        _save_topics(topics)
        return EventReply(f"已開始追蹤：<b>{escape(args)}</b>\n/updates 查看加入後的新進展；/timeline {escape(args)} 回顧已保存紀錄。\n使用完整詞組、不分大小寫比對。")
    if name == "untrack":
        if not selected:
            return EventReply("沒有追蹤這個主題。使用 /tracks 查看清單。")
        _save_topics([topic for topic in topics if topic is not selected])
        return EventReply(f"已停止追蹤：{escape(selected['keyword'])}。保存的新聞仍可查詢。")
    if name == "updates" and args:
        if not selected:
            return EventReply("沒有追蹤這個主題。請先 /track 關鍵字。")
        topics = [selected]
    if not topics:
        return EventReply("尚未追蹤任何主題。使用 /track BTC 或 /track spot ETF 開始。")
    records = _records()
    if name == "tracks":
        rows = []
        for topic in topics:
            count = sum(item["cursor"] > tuple(topic["cursor"]) and _matches(item, topic["keyword"])
                        for item in records)
            rows.append(f"• {escape(topic['keyword'])} — 新增 {count} 則")
        return EventReply("<b>追蹤清單</b>\n" + "\n".join(rows)
                          + "\n\n/updates 讀取新增進展；/timeline 關鍵字回顧。\n清單與閱讀進度由設定的聊天室共用。")
    return _updates(topics, records, args)
