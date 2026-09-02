import asyncio
import json
import os
import random
import re
import struct
import time
from collections import deque
from html import unescape
from typing import Optional

import aiohttp
import websockets

from common import (
    CONTEXT_MAX_AGE_SEC,
    CONTEXT_MAX_ITEMS,
    TIER_LEVELS,
    TIER_RANK,
    MAX_TIER_TO_SEND,
    get_logger,
    save_recent_news,
)
from gemini import GEMINI_API_KEY, call_gemini, test_gemini_connection, mask_key
from tg01 import TELEGRAM_BOT_TOKEN_01, TELEGRAM_CHAT_ID, send_telegram_message

log = get_logger("jin10")

# ─── WebSocket / keyword settings ──────────────────────────────────────────────

WS_URLS = [url.strip() for url in os.getenv("WS_URLS", "wss://wss-flash-2.jin10.com/").split(",") if url.strip()]
WS_RECONNECT_DELAY = float(os.getenv("WS_RECONNECT_DELAY", "5"))
WS_IDLE_TIMEOUT = int(os.getenv("WS_IDLE_TIMEOUT", "180"))

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

DEFAULT_KEYWORDS = [
    # --- Core crypto assets and concepts ---
    "比特币", "Bitcoin", "BTC", "以太坊", "Ethereum", "ETH",
    "加密货币", "加密貨幣", "数字货币", "虚拟货币", "币圈", "crypto", "cryptocurrency",
    "链上", "on-chain", "DeFi", "NFT", "Web3", "山寨币", "altcoin",
    "Solana", "SOL", "XRP", "Ripple", "狗狗币", "Dogecoin", "DOGE",
    "币安币", "BNB", "Cardano", "ADA", "Polkadot", "Avalanche", "AVAX",
    "Layer2", "L2",

    # --- Exchanges and institutional ecosystem ---
    "币安", "Binance", "Coinbase", "OKX", "Bybit", "Kraken", "Bitfinex",
    "火币", "Huobi", "HTX", "灰度", "Grayscale", "贝莱德", "BlackRock",
    "MicroStrategy", "Strategy", "Circle", "Tether", "USDT", "USDC", "稳定币",
    "stablecoin",

    # --- ETF and regulation ---
    "现货ETF", "比特币ETF", "以太坊ETF", "SEC", "CFTC", "证监会", "香港证监会",
    "监管", "稳定币法案", "GENIUS Act",

    # --- Market dynamics and risk events ---
    "爆仓", "清算", "做多", "做空", "杠杆", "减半", "halving",
    "黑客", "被盗", "交易所停摆", "挤兑", "脱锚", "depeg", "崩盘", "暴跌", "暴涨",

    # --- Key people ---
    "特朗普", "Trump", "马斯克", "Musk", "鲍威尔", "Powell",
    "赵长鹏", "CZ", "Saylor", "Michael Saylor", "Vitalik", "Buterin",

    # --- Macro drivers (only the core factors with a direct impact on crypto volatility) ---
    "美联储", "Fed", "FOMC", "CPI", "PCE", "非农", "通胀", "降息", "加息", "利率",
]


def load_keywords(env_name: str, fallback: list[str]) -> list[str]:
    """Supports KEYWORDS_FILE=path/to.txt to override the built-in keywords, one per line."""
    file_value = os.getenv(env_name, "").strip()
    if not file_value:
        return list(fallback)
    try:
        lines = [line.strip() for line in open(file_value, encoding="utf-8")]
    except OSError as exc:
        log.warning("Failed to read %s; using built-in keywords instead: %s", file_value, exc)
        return list(fallback)
    keywords = [line for line in lines if line and not line.startswith("#")]
    return keywords or list(fallback)


KEYWORDS = load_keywords("KEYWORDS_FILE", DEFAULT_KEYWORDS)

# ─── jin10 flash news text parsing ────────────────────────────────────────────

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
        lines.append(f"Actual: {actual}{unit}")
    if consensus:
        lines.append(f"Expected: {consensus}{unit}")
    if previous:
        lines.append(f"Previous: {previous}{unit}")
    if data.get("country"):
        lines.append(f"Market: {clean_html(str(data.get('country')))}")
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


# ─── WebSocket binary protocol ────────────────────────────────────────────────

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
        struct.pack("<i", 0),        # unsigned user ID (not logged in)
        pack_str(""),
        pack_str("chrome"),
        struct.pack("<i", 0),        # T3 user
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

def _detect_ws_header_kw() -> str:
    """Compat with websockets 12/13 using extra_headers and 14+ using additional_headers. Detected once at import time."""
    try:
        import inspect
        params = inspect.signature(websockets.connect).parameters
    except (TypeError, ValueError):
        params = {}
    return "additional_headers" if "additional_headers" in params else "extra_headers"

_WS_HEADER_KW = _detect_ws_header_kw()

def get_ws_connect_kwargs() -> dict:
    kwargs = {"origin": "https://www.jin10.com", "ping_interval": None, "open_timeout": 10}
    kwargs[_WS_HEADER_KW] = get_ws_headers()
    return kwargs


# ─── Deduplication ─────────────────────────────────────────────────────────────

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


# ─── Gemini tiering and summarization ──────────────────────────────────────────

GEMINI_PROMPT = """You are Jarvis, an elite AI advisor specializing in cryptocurrency market intelligence. Your objective is to (1) grade how much the news flash will move the crypto market, and (2) if relevant, produce a dense, refined briefing.

Analyze the provided news flash below and respond according to the rules.

# News flash:
{text}

# Step 1 — Tier Classification:
- CRITICAL: Direct and immediate impact with a high probability of causing massive short-term volatility in BTC/ETH or major crypto markets. Typically involves major market-moving events that can rapidly change liquidity, regulation, systemic risk, or institutional positioning.
  (e.g., Fed rate decisions, Spot ETF approvals/denials, SEC major regulatory enforcement, tier-1 exchange insolvency, major crypto/stablecoin hack, major stablecoin de-peg, massive institutional buy/sell, sudden systemic liquidity crisis).

- HIGH: Clear and meaningful impact on crypto markets, with a reasonable potential to affect BTC/ETH prices, sentiment, liquidity, or positioning in the short term, but unlikely to independently cause extreme or market-wide volatility.
  (e.g., CPI/NFP macro data, important Fed official remarks, significant ETF net-flow changes, major whale transfers, major national crypto regulatory policy shifts, significant institutional adoption or investment announcements, major statements from influential figures such as Trump/Musk when directly related to crypto).

- MEDIUM: Relevant to the crypto industry or market sentiment, but the direct short-term price impact on BTC/ETH is limited, uncertain, or likely to be temporary. Usually affects a specific sector, protocol, company, or group of assets rather than the broader crypto market.
  (e.g., single protocol upgrades, major-but-non-systemic exchange developments, token-specific news, moderate whale activity, crypto industry reports, partnerships, funding announcements, individual asset price movements, non-critical regulatory developments).

- LOW: Weak, indirect, niche, or negligible connection to BTC/ETH or the broader crypto market. Unlikely to materially affect short-term market sentiment, liquidity, or positioning.
  (e.g., minor protocol updates, small exchange announcements, routine company news, minor partnerships, promotional activities, low-cap token movements, opinion pieces, general industry commentary).

1. Set "relevant" to false ONLY if the news has zero connection to crypto (tier MUST be LOW).
2. Do not classify a news item as HIGH merely because it is important to the crypto industry.
3. HIGH should be reserved for events that have a credible and meaningful probability of affecting BTC/ETH or the broader crypto market in the short term.
4. When uncertain between two levels, prefer the lower level.

# Step 2 — Briefing Format Rules:
Write "message" as an HTML-formatted briefing string strictly adhering to:
1. Persona: Professional, sharp, elegant, understated loyalty. Zero fluff, zero greetings.
2. Language: Traditional Chinese ONLY (Strictly NO Simplified Chinese).
3. Strictly keep ENGLISH without Chinese translation for:
   - Geopolitical & location names (US, Israel, Ukraine, Taiwan, EU, Eurozone)
   - Institutions & key entities (Fed, OPEC, SEC, BRK, Trump, Musk, ECB)
   - Tech/Crypto/Macro terms (Layer 2, Liquidity, FVG, CPI, PCE, Bullish, Bearish, Inflation, Geopolitical Risk)
   - DO NOT append Chinese in parentheses after any English term.
4. Always use "台灣", NEVER "中國台灣".
5. Allowed HTML tags ONLY: <b>...</b>, <i>...</i>, and <code...></code>. 
   - DO NOT use <br>, <p>, <div>, or Markdown (*, #).
   - Use plain JSON escaped newline characters "\n" for line breaks inside the string.

# "message" String Structure:
<b>(News Title translated to Traditional Chinese)</b>\n\n(One-sentence core summary, natural human tone)\n\n<b>Crypto</b>\n(Short-term analysis in 1 concise sentence)\n\n<b>總體經濟影響</b>\n(Optional: 1 sentence ONLY if impact is massive; otherwise leave completely empty)\n\n<b>世界發展影響</b>\n(Optional: 1 sentence ONLY if impact is massive; otherwise leave completely empty)\n\n<b>Keywords</b> | <code>Term A</code>, <code>Term B</code>, <code>Term C</code>

# Output Format:
Respond with ONLY a raw JSON object (no markdown fences, no commentary) matching this shape:
{{"tier": <"CRITICAL"|"HIGH"|"MEDIUM"|"LOW">, "relevant": <true|false>, "message": "<the HTML briefing string, or a short reason if not relevant>"}}
"""

GEMINI_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "tier": {"type": "STRING", "enum": TIER_LEVELS},
        "relevant": {"type": "BOOLEAN"},
        "message": {"type": "STRING"},
    },
    "required": ["tier", "relevant", "message"],
}

async def summarize_with_gemini(session: aiohttp.ClientSession, text: str) -> Optional[dict]:
    """Call Gemini to get tiering and summary. Returns {"tier": str|None, "relevant": bool, "message": str}; returns None on failure."""
    raw_text = await call_gemini(session, GEMINI_PROMPT.format(text=text), response_schema=GEMINI_RESPONSE_SCHEMA)
    if not raw_text:
        return None
    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        log.warning("Gemini returned invalid JSON: %s", raw_text[:300])
        return None
    tier = str(result.get("tier") or "").strip().upper()
    if tier not in TIER_RANK:
        tier = None
    return {
        "tier": tier,
        "relevant": bool(result.get("relevant", True)),
        "message": str(result.get("message", "")).strip(),
    }


# ─── Recent flash context (for telegram_assistant.py Q&A) ───────────────────────────

recent_news: deque[dict] = deque(maxlen=CONTEXT_MAX_ITEMS)

# Set once at startup by test_gemini_connection(); when False, handle_item() skips
# calling Gemini on every item instead of retrying (and failing) per-message.
GEMINI_AVAILABLE = False

def remember_news(title: str, content: str, tier: Optional[str]) -> None:
    now = time.time()
    recent_news.append({"ts": now, "title": title, "content": content, "tier": tier})
    while recent_news and now - recent_news[0]["ts"] > CONTEXT_MAX_AGE_SEC:
        recent_news.popleft()
    save_recent_news(list(recent_news))


# ─── Message assembly ──────────────────────────────────────────────────────────

TIER_BADGES = {"CRITICAL", "HIGH", "MEDIUM"}

def format_message(summary: str, tier: Optional[str] = None) -> str:
    parts = []
    if tier in TIER_BADGES:
        parts.append(tier)
    if summary:
        parts.append(summary)
    return "\n".join(parts)


# ─── Main flow ────────────────────────────────────────────────────────────────

async def handle_item(session: aiohttp.ClientSession, item: dict) -> None:
    title, content = item_text(item)
    full_text = f"{title} {content}".strip()
    if not full_text:
        return
    if not match_keywords(full_text):
        return

    log.info("Keyword match: %s", (title or content)[:60])

    tier: Optional[str] = None
    summary = ""
    if GEMINI_API_KEY and GEMINI_AVAILABLE:
        result = await summarize_with_gemini(session, full_text)
        if result is None:
            # Gemini failed; skip tier filtering and send the original title/content as a fallback
            log.warning("Gemini tiering failed; broadcasting original content directly: %s", (title or content)[:60])
            remember_news(title, content, None)
            summary = title or content
        else:
            tier = result["tier"]
            remember_news(title, content, tier)
            # Unknown/unparseable tier is treated as the lowest priority (LOW) rather than
            # bypassing the filter entirely, so MAX_TIER_TO_SEND still applies to it.
            tier_rank = TIER_RANK.get(tier, TIER_RANK["LOW"])
            if not result["relevant"] or tier_rank > MAX_TIER_TO_SEND:
                log.info("Gemini decided tier=%s relevant=%s; skipping push: %s",
                          tier, result["relevant"], (title or content)[:60])
                return
            summary = result["message"]
    else:
        remember_news(title, content, None)
        summary = title or content

    msg = format_message(summary, tier=tier)
    ok = await send_telegram_message(session, TELEGRAM_CHAT_ID, msg)
    log.info("Telegram send %s", "successful" if ok else "failed")


async def ws_loop(session: aiohttp.ClientSession) -> None:
    log.info("Attempting to establish WebSocket connection...")
    while True:
        ws_url = random.choice(WS_URLS)
        try:
            async with websockets.connect(ws_url, **get_ws_connect_kwargs()) as ws:
                log.info("WebSocket connected: %s", ws_url)
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
                            log.info("WebSocket login packet sent")
                            continue
                        packet = xor_payload(bytes(raw), secret)
                        code, data = parse_ws_packet(packet)
                    except Exception as exc:
                        log.debug("WebSocket message parsing failed: %s", exc)
                        continue

                    if code == 1201:
                        await ws.send(b"")
                        continue

                    if code in {1000, 1100} and isinstance(data, dict):
                        if data.get("action") in {1, 2} and is_new(data):
                            await handle_item(session, data)
                    elif code == 1200 and isinstance(data, list):
                        # When the connection opens, a batch of historical flash news is sent; it is only used to warm the deduplication cache, not processed individually to avoid duplicate spam
                        if not skipped_initial_list:
                            for entry in data:
                                if isinstance(entry, dict):
                                    is_new(entry)
                            skipped_initial_list = True
                            log.info("Initial historical list warmed for deduplication: %d entries", len(data))
                            continue
                        for entry in data:
                            if isinstance(entry, dict) and entry.get("action") in {1, 2} and is_new(entry):
                                await handle_item(session, entry)
        except asyncio.TimeoutError:
            log.warning("WebSocket received no messages for %.0fs; reconnecting", WS_IDLE_TIMEOUT)
            await asyncio.sleep(WS_RECONNECT_DELAY)
        except Exception as exc:
            log.warning(
                "WebSocket disconnected: %s: %s; reconnecting in %ss",
                type(exc).__name__, exc, WS_RECONNECT_DELAY,
            )
            log.debug("Full traceback:", exc_info=True)
            await asyncio.sleep(WS_RECONNECT_DELAY)


async def main() -> None:
    print()
    # print(f"GEMINI_API_KEY : {mask_key(GEMINI_API_KEY)}")
    # print(f"TELEGRAM_BOT_TOKEN_01 : {mask_key(TELEGRAM_BOT_TOKEN_01)}")
    # print(f"TELEGRAM_CHAT_ID : {mask_key(TELEGRAM_CHAT_ID)}")
    # print()
    global GEMINI_AVAILABLE
    async with aiohttp.ClientSession() as session:
        GEMINI_AVAILABLE = await test_gemini_connection(session)
        if not GEMINI_AVAILABLE:
            log.warning("Gemini validation failed; subsequent flash updates will skip the summary step.")

        if not TELEGRAM_BOT_TOKEN_01 or not TELEGRAM_CHAT_ID:
            log.warning("TELEGRAM_BOT_TOKEN_01 / TELEGRAM_CHAT_ID are not set; Telegram push notifications will be skipped")

        await ws_loop(session)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Stopped manually")