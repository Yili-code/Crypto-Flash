import asyncio
import json
import logging
import os
import random
import re
import struct
from html import escape, unescape
from typing import Optional

import aiohttp
import websockets
from dotenv import load_dotenv

load_dotenv(override=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("jin10")

# ─── 配置 ───────────────────────────────────────────────────────────────────

TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

WS_URLS = [url.strip() for url in os.getenv("WS_URLS", "wss://wss-flash-2.jin10.com/").split(",") if url.strip()]
WS_RECONNECT_DELAY = float(os.getenv("WS_RECONNECT_DELAY", "5"))
WS_IDLE_TIMEOUT = int(os.getenv("WS_IDLE_TIMEOUT", "180"))

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# 關鍵詞命中時才推播（空列表 = 全推）
DEFAULT_KEYWORDS = [
    # --- 央行與宏觀（僅保留核心驅動因子） ---
    "美联储", "Fed", "CPI", "通胀", "降息",

    # --- 加密貨幣與機構生態 ---
    "比特币", "Bitcoin", "BTC", "以太坊", "ETH", "加密", "crypto", "稳定币",
    "ETF", "现货ETF", "贝莱德", "爆仓",
    "MicroStrategy", "币安", "Binance", "Coinbase", "Tether", "Circle",

    # --- 關鍵人物與風險資產（僅保留巨頭與政經焦點） ---
    "特朗普", "Trump", "马斯克", "Musk", "英伟达", "NVDA"
]


def load_keywords(env_name: str, fallback: list[str]) -> list[str]:
    """可用 KEYWORDS_FILE=path/to.txt 覆寫，一行一個關鍵詞。"""
    file_value = os.getenv(env_name, "").strip()
    if not file_value:
        return list(fallback)
    try:
        lines = [line.strip() for line in open(file_value, encoding="utf-8")]
    except OSError as exc:
        log.warning("%s 讀取失敗，使用內建關鍵詞：%s", file_value, exc)
        return list(fallback)
    keywords = [line for line in lines if line and not line.startswith("#")]
    return keywords or list(fallback)

KEYWORDS = load_keywords("KEYWORDS_FILE", DEFAULT_KEYWORDS)

# ─── jin10 快訊文字解析 ──────────────────────────────────────────────────────

def clean_html(raw: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()

def item_data(item: dict) -> dict:
    data = item.get("data", {})
    return data if isinstance(data, dict) else {}

def clean_number(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "none", "null"} else text

def indicator_item_text(item: dict) -> tuple[str, str]:

    if item.get("type") != 1:
        return "", ""
    data = item_data(item)
    name = clean_html(str(data.get("name") or ""))
    measure = clean_html(str(data.get("measure") or ""))
    period = clean_html(str(data.get("time_period") or ""))
    if not name and not measure:
        return "", ""
    title = " ".join(part for part in [name, period, measure] if part)
    actual = clean_number(data.get("actual"))
    unit = clean_html(str(data.get("unit") or ""))
    consensus = clean_number(data.get("consensus"))
    previous = clean_number(data.get("previous"))
    lines = []
    if actual:
        lines.append(f"公布值：{actual}{unit}")
    if consensus:
        lines.append(f"預期：{consensus}{unit}")
    if previous:
        lines.append(f"前值：{previous}{unit}")
    if data.get("country"):
        lines.append(f"市場：{clean_html(str(data.get('country')))}")
    return title, "\n".join(lines)

def item_text(item: dict) -> tuple[str, str]:
    data = item_data(item)
    raw_title = str(data.get("title") or item.get("title") or "")
    raw_content = str(data.get("content") or item.get("content") or "")
    title = clean_html(raw_title)
    content = clean_html(raw_content)
    if not title:
        match = re.match(r"\s*(?:<b>)?【(?:<b>)?(.+?)(?:</b>)?】(?:</b>)?(.*)", raw_content, re.S)
        if match:
            title = clean_html(match.group(1))
            content = clean_html(match.group(2))
    if not title and not content:
        title, content = indicator_item_text(item)
    return title, content

def match_keywords(text: str) -> bool:
    if not KEYWORDS:
        return True
    return any(k in text for k in KEYWORDS)


# ─── WebSocket 二進位協議 ────────────────────────────────────────────────────

def pack_str(value: str) -> bytes:
    raw = value.encode("utf-8")
    return struct.pack("<H", len(raw)) + raw

def unpack_str(buffer: memoryview, offset: int) -> tuple[str, int]:
    size = struct.unpack_from("<H", buffer, offset)[0]
    offset += 2
    raw = buffer[offset:offset + size].tobytes()
    offset += size
    return raw.decode("utf-8"), offset

def xor_payload(payload: bytes, key: str) -> bytes:
    if not payload or not key:
        return payload
    seed = ord(key[0])
    key_codes = [ord(ch) for ch in key]
    key_len = len(key_codes)
    return bytes(byte ^ key_codes[(idx + seed) % key_len] for idx, byte in enumerate(payload))

def build_ws_login(key: str, last_id: Optional[str] = None) -> bytes:
    payload = b"".join([
        struct.pack("<h", 4002),
        struct.pack("<i", 0),        # 未登陸用戶 ID
        pack_str(""),
        pack_str("chrome"),
        struct.pack("<i", 0),        # T3 用戶
        pack_str("web"),
        pack_str(last_id or ""),
    ])
    return xor_payload(payload, key)

def parse_ws_packet(payload: bytes) -> tuple[int, object]:
    buffer = memoryview(payload)
    code = struct.unpack_from("<h", buffer, 0)[0]
    offset = 2
    if code in {1000, 1001, 1002, 1003, 1100, 4002, 1005}:
        text, _ = unpack_str(buffer, offset)
        return code, json.loads(text)
    if code == 1200:
        count = struct.unpack_from("<i", buffer, offset)[0]
        offset += 4
        items = []
        for _ in range(count):
            text, offset = unpack_str(buffer, offset)
            items.insert(0, json.loads(text))
        return code, items
    return code, None

def get_ws_headers() -> dict:
    return {
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
        "User-Agent": random.choice(UA_POOL),
    }

def get_ws_connect_kwargs() -> dict:
    """兼容 websockets 12/13 的 extra_headers 和 14+ 的 additional_headers。"""
    kwargs = {"origin": "https://www.jin10.com", "ping_interval": None, "open_timeout": 10}
    try:
        import inspect
        params = inspect.signature(websockets.connect).parameters
    except (TypeError, ValueError):
        params = {}
    header_arg = "additional_headers" if "additional_headers" in params else "extra_headers"
    kwargs[header_arg] = get_ws_headers()
    return kwargs


# ─── 去重 ───────────────────────────────────────────────────────────────────

seen_ids: dict[str, None] = {}

def is_new(item: dict) -> bool:
    fid = str(item.get("id", ""))
    if not fid or fid in seen_ids:
        return False
    seen_ids[fid] = None
    if len(seen_ids) > 2000:
        for key in list(seen_ids)[:500]:
            del seen_ids[key]
    return True


# ─── Gemini 摘要 ────────────────────────────────────────────────────────────

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_PROMPT = """You are Jarvis, an elite AI advisor to Sir. Your objective is to deliver real-time, highly dense financial intelligence briefings with a refined, precise, and sophisticated persona.

Analyze the provided news flash ({text}) and present your briefing in Traditional Chinese according to the structural rules below.

# Tone & Protocol Rules:
1. Persona: Professional, sharp, elegant, and understatedly loyal.
2. Zero Fluff: Direct-to-point. No greeting filler like "Hello", "Here is your summary", or generic conversational pleasantries.
3. Primary Language: Traditional Chinese (絕對不能出現簡體中文).
4. English Preservation Rules:
   - Keep the following categories STRICTLY in English without translation:
     * Geopolitical & Location Names (e.g., US, Israel, Ukraine, Taiwan, EU).
     * Financial Institutions & Key Entities (e.g., Fed, OPEC, SEC, BRK, Trump).
     * Tech, Crypto, & Macroeconomic Terms (e.g., Layer 2, Liquidity, FVG, CPI, PCE, Bullish).
   - Absolute Prohibition: Do NOT append Chinese translations in parentheses or quotes after any English terms (e.g., write "Trump", NOT "Trump (川普)").
5. Do NOT output「中國台灣」, always use「台灣」
6. Only standard HTML bold tags (<b>...</b>) are allowed. Do NOT output any other HTML tags.

# Output Structure:
<b># (New title)</b>

<b>(簡單用一句話總結新聞)</b> 

---
<b>Crypto 短期走勢與長期趨勢</b>
# Short-term | (Analysis content, 用簡單的方式精簡說明)

# Long-term | (Analysis content, 用簡單的方式精簡說明)

<b>總體經濟 / 世界發展影響</b>
(Analysis content, 一句話簡單說明即可)

<b>科技影響</b>
(Include this section ONLY IF the news explicitly involves Technology, AI, or Infrastructure; otherwise, omit this entire header and content completely)

<b>Keywords | Term A, Term B, Term C</b>
"""

async def summarize_with_gemini(session: aiohttp.ClientSession, text: str) -> str:
    if not GEMINI_API_KEY:
        return ""
    url = GEMINI_URL.format(model=GEMINI_MODEL)

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY
    }

    payload = {
        "contents": [{"parts": [{"text": GEMINI_PROMPT.format(text=text)}]}],
    }

    try:
        async with session.post(
            url,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                log.warning("Gemini 呼叫失敗：status=%s body=%s", resp.status, body[:300])
                return ""
            data = await resp.json()
            candidates = data.get("candidates") or []
            if not candidates:
                return ""
            parts = candidates[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts).strip()
    except Exception as exc:
        log.warning("Gemini 呼叫異常：%s", exc)
        return ""


# ─── Telegram 推播 ──────────────────────────────────────────────────────────

async def send_telegram(session: aiohttp.ClientSession, text: str) -> bool:
    if not TG_TOKEN or not TG_CHAT_ID:
        log.warning("Telegram 未配置，略過發送：\n%s", text)
        return False
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    for attempt in range(1, 3):
        try:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return True
                body = await resp.text()
                log.warning("Telegram 發送失敗：status=%s attempt=%s body=%s", resp.status, attempt, body[:300])
        except Exception as exc:
            log.warning("Telegram 發送異常：attempt=%s error=%s", attempt, exc)
        await asyncio.sleep(1.5)
    return False

def format_message(title: str, content: str, summary: str) -> str:
    parts = [""]
    if summary:
        parts.append(f"{(summary)}")
    if content:
        parts.append(f"\n<b>Source</b>\n{escape(content)}")
    return "\n".join(parts)


# ─── 主流程 ─────────────────────────────────────────────────────────────────

async def handle_item(session: aiohttp.ClientSession, item: dict) -> None:
    title, content = item_text(item)
    full_text = f"{title} {content}".strip()
    if not full_text:
        return
    if not match_keywords(full_text):
        return

    log.info("命中關鍵詞：%s", (title or content)[:60])
    summary = await summarize_with_gemini(session, full_text)
    msg = format_message(title, content, summary)
    ok = await send_telegram(session, msg)
    log.info("Telegram 發送%s", "成功" if ok else "失敗")


async def ws_loop(session: aiohttp.ClientSession) -> None:
    log.info("嘗試建立 WebSocket 連接 …")
    while True:
        ws_url = random.choice(WS_URLS)
        try:
            async with websockets.connect(ws_url, **get_ws_connect_kwargs()) as ws:
                log.info("WebSocket 已連接：%s", ws_url)
                secret = ""
                skipped_initial_list = False
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=WS_IDLE_TIMEOUT)
                    if not isinstance(raw, (bytes, bytearray)):
                        continue
                    try:
                        if not secret:
                            packet = bytes(raw)
                            if len(packet) < 12:
                                continue
                            _, seed_b, seed_a = struct.unpack_from("<III", packet, 0)
                            secret = f"{seed_a}.{seed_b}"
                            await ws.send(build_ws_login(secret))
                            log.info("WebSocket 登入包已發送")
                            continue
                        packet = xor_payload(bytes(raw), secret)
                        code, data = parse_ws_packet(packet)
                    except Exception as exc:
                        log.debug("WebSocket 訊息解析失敗：%s", exc)
                        continue

                    if code == 1201:
                        await ws.send(b"")
                        continue

                    if code in {1000, 1100} and isinstance(data, dict):
                        if data.get("action") in {1, 2} and is_new(data):
                            await handle_item(session, data)
                    elif code == 1200 and isinstance(data, list):
                        # 剛連線時會收到一批歷史快訊，僅用來預熱去重，不逐條處理避免洗版
                        if not skipped_initial_list:
                            for entry in data:
                                if isinstance(entry, dict):
                                    is_new(entry)
                            skipped_initial_list = True
                            log.info("初始歷史列表已預熱去重：%d 條", len(data))
                            continue
                        for entry in data:
                            if isinstance(entry, dict) and entry.get("action") in {1, 2} and is_new(entry):
                                await handle_item(session, entry)
        except asyncio.TimeoutError:
            log.warning("WebSocket %.0fs 未收到訊息，主動重連", WS_IDLE_TIMEOUT)
            await asyncio.sleep(WS_RECONNECT_DELAY)
        except Exception as exc:
            log.warning("WebSocket 斷線：%s，%ss 後重連", exc, WS_RECONNECT_DELAY)
            await asyncio.sleep(WS_RECONNECT_DELAY)

async def test_gemini_connection(session: aiohttp.ClientSession) -> bool:
    if not GEMINI_API_KEY:
        log.warning("未設置 GEMINI_API_KEY")
        return False

    url = GEMINI_URL.format(model=GEMINI_MODEL)
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY
    }
    payload = {"contents": [{"parts": [{"text": "Ping"}]}]}

    try:
        async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                log.info("Gemini API Key 驗證成功！連線正常。")
                return True
            body = await resp.text()
            log.error("Gemini API Key 驗證失敗 (Status %s): %s", resp.status, body[:200])
            return False
    except Exception as exc:
        log.error("Gemini 連線測試異常: %s", exc)
        return False
    
async def main() -> None:
    async with aiohttp.ClientSession() as session:
        gemini_ok = await test_gemini_connection(session)
        if not gemini_ok:
            log.warning("Gemini 驗證未通過，後續快訊將跳過摘要步驟。")

        if not TG_TOKEN or not TG_CHAT_ID:
            log.warning("未設置 TG_TOKEN / TG_CHAT_ID，Telegram 推播會被跳過")

        await ws_loop(session)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("已手動停止")
