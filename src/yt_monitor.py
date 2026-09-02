import asyncio
import json
import os
import xml.etree.ElementTree as ET
from html import escape as html_escape
from pathlib import Path
from typing import Optional

import aiohttp

from common import BASE_DIR, get_logger
from gemini import GEMINI_API_KEY, call_gemini
from tg import TELEGRAM_BOT_TOKEN_02, TELEGRAM_CHAT_ID, send_telegram_message

log = get_logger("yt-monitor")

# ─── 設定 ───────────────────────────────────────────────────────────────────

CHANNELS_CONFIG_FILE = Path(os.getenv("YT_CHANNELS_CONFIG", str(BASE_DIR / "config" / "yt_channels.json")))
DEFAULT_MAX_NEW_PER_RUN = int(os.getenv("YT_MAX_NEW_PER_RUN", "3"))
SEEN_STATE_FILE = Path(os.getenv("YT_SEEN_STATE_FILE", str(BASE_DIR / "data" / "yt_seen_ids.json")))
MAX_SEEN_IDS_PER_CHANNEL = int(os.getenv("YT_MAX_SEEN_IDS", "300"))

ATOM_NS = "{http://www.w3.org/2005/Atom}"
YT_NS = "{http://www.youtube.com/xml/schemas/2015}"

SUMMARY_PROMPT = """請完整觀看這部 YouTube 影片，並用繁體中文整理成「5 個重點」。

規則：
1. 只能輸出 5 行，每行一個重點。
2. 不要輸出 5 行以外的任何文字（不要標題、不要總結段落）。
3. Persona: Professional, sharp, elegant, understated loyalty. Zero fluff, zero greetings.
4. Language: Traditional Chinese ONLY (Strictly NO Simplified Chinese).
5. Strictly keep ENGLISH without Chinese translation for:
   - Geopolitical & location names (US, Israel, Ukraine, Taiwan, EU, Eurozone)
   - Institutions & key entities (Fed, OPEC, SEC, BRK, Trump, Musk, ECB)
   - Tech/Crypto/Macro terms (Layer 2, Liquidity, FVG, CPI, PCE, Bullish, Bearish, Inflation, Geopolitical Risk)
   - DO NOT append Chinese in parentheses after any English term.
6. Always use "台灣", NEVER "中國台灣".

# "message" String Structure:
(One-sentence core summary, natural human tone)

<b>01</b>
(重點一)
(空一行)
<b>02</b>
(重點二)
(空一行)
<b>03</b>
(重點三)
(空一行)
<b>04</b>
(重點四)
(空一行)
<b>05</b>
(重點五)
(空一行)
<b>Keywords</b> | <code>Term A</code>
"""

# ─── 頻道設定 ───────────────────────────────────────────────────────────────

def load_channel_configs() -> list[dict]:
    if not CHANNELS_CONFIG_FILE.exists():
        log.error("找不到頻道設定檔：%s", CHANNELS_CONFIG_FILE)
        return []
    try:
        raw = json.loads(CHANNELS_CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.error("頻道設定檔讀取/解析失敗：%s", exc)
        return []
    if not isinstance(raw, list):
        log.error("頻道設定檔格式錯誤，最外層必須是陣列。")
        return []

    configs = []
    seen_names = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            log.warning("頻道設定第 %d 項不是物件，跳過。", i)
            continue

        name = str(item.get("name", "")).strip()
        channel_id = str(item.get("channel_id", "")).strip()
        if not name or not channel_id:
            log.warning("頻道設定第 %d 項缺少 name 或 channel_id，跳過。", i)
            continue

        if name in seen_names:
            log.warning("頻道設定的 name「%s」重複，跳過第 %d 項（會導致已讀狀態互相覆蓋）。", name, i)
            continue
        seen_names.add(name)
        configs.append({
            "name": name,
            "channel_id": channel_id,
            "system_prompt": str(item.get("system_prompt", "") or "").strip(),
            "max_new_per_run": int(item.get("max_new_per_run") or DEFAULT_MAX_NEW_PER_RUN),
        })
    return configs


# ─── 已處理清單的讀寫（多頻道共用一個檔案，用 name 分 key） ─────────────────

def load_seen_state() -> dict[str, list[str]]:
    if not SEEN_STATE_FILE.exists():
        return {}
    try:
        state = json.loads(SEEN_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("讀取已處理影片清單失敗：%s", exc)
        return {}
    if not isinstance(state, dict):
        return {}
    return {
        str(k): [i for i in v if isinstance(i, str)]
        for k, v in state.items() if isinstance(v, list)
    }


def save_seen_state(state: dict[str, list[str]]) -> None:
    try:
        SEEN_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        trimmed = {k: v[-MAX_SEEN_IDS_PER_CHANNEL:] for k, v in state.items()}
        tmp_path = SEEN_STATE_FILE.with_suffix(SEEN_STATE_FILE.suffix + ".tmp")
        tmp_path.write_text(json.dumps(trimmed, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(SEEN_STATE_FILE)
    except OSError as exc:
        log.warning("寫入已處理影片清單失敗：%s", exc)


# ─── RSS 解析 ───────────────────────────────────────────────────────────────

def parse_feed(xml_text: str) -> tuple[str, list[dict]]:
    """回傳 (頻道名稱, [{"video_id", "title", "link", "published"}, ...])，影片由舊到新排序。"""
    root = ET.fromstring(xml_text)
    
    # 提取頻道名稱
    channel_title_el = root.find(f"{ATOM_NS}title")
    channel_title = (channel_title_el.text or "").strip() if channel_title_el is not None else "Unknown Channel"
    
    entries = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        video_id_el = entry.find(f"{YT_NS}videoId")
        video_id = (video_id_el.text or "").strip() if video_id_el is not None else ""
        if not video_id:
            continue
        title_el = entry.find(f"{ATOM_NS}title")
        title = (title_el.text or "").strip() if title_el is not None else ""
        link_el = entry.find(f"{ATOM_NS}link")
        link = (link_el.get("href") if link_el is not None else "") or f"https://www.youtube.com/watch?v={video_id}"
        published_el = entry.find(f"{ATOM_NS}published")
        published = (published_el.text or "").strip() if published_el is not None else ""
        entries.append({"video_id": video_id, "title": title, "link": link, "published": published})
    entries.reverse()  # feed 本身是新到舊，反轉成舊到新，推播順序才符合時間先後
    return channel_title, entries


async def fetch_feed(session: aiohttp.ClientSession, rss_url: str) -> Optional[str]:
    try:
        async with session.get(rss_url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                log.warning("RSS 讀取失敗：status=%s url=%s", resp.status, rss_url)
                return None
            return await resp.text()
    except Exception as exc:
        log.warning("RSS 讀取異常：%s", exc)
        return None


# ─── Gemini 摘要 ────────────────────────────────────────────────────────────

async def summarize_video(
    session: aiohttp.ClientSession,
    video_url: str,
    system_prompt: str = "",
) -> Optional[str]:
    if not GEMINI_API_KEY:
        return None

    return await call_gemini(
        session,
        SUMMARY_PROMPT,
        system_instruction=system_prompt or None,
        extra_parts=[{"file_data": {"file_uri": video_url}}],
        timeout=90,
    )


# ─── 訊息組裝 ───────────────────────────────────────────────────────────────

def format_message(channel_title: str, title: str, link: str, summary: Optional[str]) -> str:
    if summary:
        return f"「{title}」\n#{channel_title}\n\n{summary}\n\n<b>Source</b> {link}"
    return (
        f"<b>新影片</b>：{html_escape(title, quote=False)}\n\n"
        f"{link}\n\n"
        "（Gemini 摘要失敗，請直接點連結觀看）"
    )


# ─── 單一頻道的處理流程 ──────────────────────────────────────────────────────

async def process_channel(session: aiohttp.ClientSession, cfg: dict, seen_state: dict[str, list[str]]) -> None:
    name = cfg["name"]

    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={cfg['channel_id']}"
    xml_text = await fetch_feed(session, rss_url)
    if xml_text is None:
        return

    try:
        channel_title, entries = parse_feed(xml_text)
    except ET.ParseError as exc:
        log.warning("[%s] RSS 解析失敗：%s", name, exc)
        return

    if not entries:
        log.info("[%s] RSS 目前沒有任何影片。", name)
        return

    seen_ids = seen_state.get(name, [])

    if not seen_ids:
        seen_state[name] = [e["video_id"] for e in entries]
        save_seen_state(seen_state)
        log.info("[%s] 初始化完成，已預熱去重 %d 部影片，不會為既有影片發送通知。", name, len(entries))
        return

    seen_set = set(seen_ids)
    new_entries = [e for e in entries if e["video_id"] not in seen_set]

    if not new_entries:
        log.info("[%s] 沒有偵測到新影片。", name)
        return

    max_new = cfg["max_new_per_run"]
    if len(new_entries) > max_new:
        skipped = new_entries[:-max_new]
        log.warning("[%s] 一次偵測到 %d 部新影片，超過上限 %d，只處理最新的 %d 部，其餘標記為已讀不推播。",
                    name, len(new_entries), max_new, max_new)
        seen_ids.extend(e["video_id"] for e in skipped)
        new_entries = new_entries[-max_new:]

    for entry in new_entries:
        log.info("[%s] 發現新影片：%s", name, entry["title"][:60])
        summary = await summarize_video(session, entry["link"], cfg["system_prompt"])
        if summary is None:
            log.warning("[%s] Gemini 摘要失敗，改用純連結推播：%s", name, entry["title"][:60])
        msg = format_message(channel_title, entry["title"], entry["link"], summary)
        ok = await send_telegram_message(session, TELEGRAM_CHAT_ID, msg, TELEGRAM_BOT_TOKEN_02)
        log.info("[%s] Telegram 發送%s：%s", name, "成功" if ok else "失敗", entry["title"][:60])
        # 每處理完一部就存一次，避免中途失敗時下次重新執行又重複推播已經發過的影片。
        seen_ids.append(entry["video_id"])
        seen_state[name] = seen_ids
        save_seen_state(seen_state)


# ─── 主流程（跑一次就結束，依序處理每個頻道） ────────────────────────────────

async def main() -> None:
    configs = load_channel_configs()
    if not configs:
        log.error("沒有任何有效的頻道設定，結束。請檢查 %s", CHANNELS_CONFIG_FILE)
        return

    log.info("讀到 %d 個頻道設定：%s", len(configs), ", ".join(c["name"] for c in configs))

    seen_state = load_seen_state()
    async with aiohttp.ClientSession() as session:
        for cfg in configs:
            try:
                await process_channel(session, cfg, seen_state)
            except Exception as exc:
                log.error("[%s] 處理過程發生未預期例外：%s", cfg["name"], exc)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("已手動停止")