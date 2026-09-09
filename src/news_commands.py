"""On-demand queries over the saved news context; no network or model calls."""

import math
import re
import time
from datetime import datetime, timedelta, timezone
from html import escape

from common import CONTEXT_MAX_AGE_SEC, TIER_LEVELS, load_recent_news
from daily_digest import build_digest, previous_day

DISPLAY_TZ = timezone(timedelta(hours=8))
MAX_RESULTS = 10
MESSAGE_BUDGET = 3500
HELP_TEXT = """<b>Crypto Flash 指令</b>
/news — 最近 5 則快訊
/news 10 — 最近 10 則（最多 10 則）
/search BTC — 搜尋標題與內文，不分大小寫
/search spot ETF — 搜尋完整詞組
/important — 查看 HIGH、CRITICAL 快訊
/important 10 — 最多顯示 10 則重要快訊
/status — 查看新聞資料筆數與新鮮度
/digest — 昨日重點，依重要性排序
/digest today — 今日截至目前的重點
/digest 2026-09-09 — 指定日期（限保存資料）
/track BTC — 追蹤關鍵字的新進展
/tracks — 追蹤清單與未讀筆數
/timeline BTC — 最近 72 小時的事件時間線
/updates — 只讀追蹤主題的新增進展
/updates BTC — 只讀指定主題的新增進展
/untrack BTC — 停止追蹤
/ask 問題 — 交給 Gemini 分析
/help — 顯示指令說明

查詢使用已保存的近期新聞，時間為 UTC+8。
新聞查詢不需要 Gemini；顯示的是來源摘錄，並非 AI 摘要。"""


def parse_command(text: str, bot_username: str) -> tuple[str, str] | None:
    text = (text or "").strip()
    match = re.match(r"^/([A-Za-z0-9_]+)(?:@([A-Za-z0-9_]+))?(?=\s|$)", text)
    if not match:
        return None
    name, recipient = match.groups()
    if recipient and recipient.casefold() != bot_username.casefold():
        return None
    return name, text[match.end():].strip()


def _recent_items() -> list[dict]:
    now = time.time()
    items = []
    for item in load_recent_news():
        ts = item.get("ts")
        if isinstance(ts, bool) or not isinstance(ts, (int, float)) or not math.isfinite(ts):
            continue
        if not 0 <= now - ts <= CONTEXT_MAX_AGE_SEC:
            continue
        title = str(item.get("title") or "").strip()
        content = str(item.get("content") or "").strip()
        if title or content:
            items.append({"ts": ts, "title": title, "content": content, "tier": item.get("tier")})
    return sorted(items, key=lambda item: item["ts"], reverse=True)


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _render_results(items: list[dict], heading: str, limit: int) -> str:
    if not items:
        return f"<b>{escape(heading)}</b>\n目前保存的近期新聞中沒有符合條件的資料。"
    rows = []
    for item in items[:limit]:
        clock = datetime.fromtimestamp(item["ts"], DISPLAY_TZ).strftime("%m/%d %H:%M")
        tier = item["tier"] if item["tier"] in TIER_LEVELS else "未分級"
        title = item["title"] or item["content"]
        row = f"{clock} · {tier}\n<b>{escape(_clip(title, 100))}</b>"
        if item["title"] and item["content"] and item["content"] != item["title"]:
            row += "\n" + escape(_clip(item["content"], 160))
        # Keep complete rows and HTML entities; reserve room for the heading/footer.
        if sum(len(part.encode("utf-16-le")) // 2 for part in rows + [row]) > MESSAGE_BUDGET - 700:
            break
        rows.append(row)
    return (
        f"<b>{escape(heading)}</b>\n"
        f"顯示 {len(rows)} / {len(items)} 則 · UTC+8 · 來源摘錄\n\n"
        + "\n\n".join(rows)
    )


def local_command_reply(text: str, bot_username: str) -> str | None:
    command = parse_command(text, bot_username)
    if command is None:
        return None
    name, args = command
    if name in {"start", "help"}:
        return HELP_TEXT
    if name == "digest":
        if not args:
            day = previous_day()
        elif args == "today":
            day = datetime.now(DISPLAY_TZ).date()
        else:
            try:
                day = datetime.strptime(args, "%Y-%m-%d").date()
            except ValueError:
                return "用法：/digest、/digest today 或 /digest YYYY-MM-DD。"
        return build_digest(day)
    if name not in {"news", "search", "important", "status"}:
        return None
    limit = 5
    if name in {"news", "important"} and args:
        if not re.fullmatch(r"[0-9]{1,2}", args) or not 1 <= int(args) <= MAX_RESULTS:
            return f"用法：/{name} [1–10]，例如 /{name} 5。"
        limit = int(args)
    if name == "search" and not args:
        return "用法：/search 關鍵字，例如 /search BTC 或 /search spot ETF。"
    if name == "search" and len(args) > 100:
        return "搜尋詞請限制在 100 個字元內。"
    if name == "status" and args:
        return "用法：/status（不需要參數）。"
    items = _recent_items()
    if name == "status":
        counts = {tier: sum(item["tier"] == tier for item in items) for tier in TIER_LEVELS}
        latest = "尚無近期資料"
        if items:
            stamp = datetime.fromtimestamp(items[0]["ts"], DISPLAY_TZ).strftime("%m/%d %H:%M")
            age = max(0, int((time.time() - items[0]["ts"]) // 60))
            latest = f"{stamp} UTC+8（{age} 分鐘前）"
        distribution = " · ".join(f"{tier} {count}" for tier, count in counts.items())
        unknown = len(items) - sum(counts.values())
        return (
            f"<b>新聞資料狀態</b>\n保存範圍：最近 {CONTEXT_MAX_AGE_SEC / 3600:g} 小時\n"
            f"可查詢：{len(items)} 則\n最新紀錄：{latest}\n"
            f"{distribution}\n未分級 {unknown}\n\n"
            "以上反映本次問答服務可讀取的新聞資料，不代表監控器或 Gemini 的即時連線狀態。"
        )
    if name == "search":
        query = args.casefold()
        items = [item for item in items if query in f"{item['title']} {item['content']}".casefold()]
        return _render_results(items, f"搜尋：{args}", MAX_RESULTS)
    if name == "important":
        items = [item for item in items if item["tier"] in ("HIGH", "CRITICAL")]
        return _render_results(items, "重要快訊", limit)
    return _render_results(items, "近期快訊", limit)
