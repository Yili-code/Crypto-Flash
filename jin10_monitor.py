import asyncio
import json
import logging
import os
import random
import re
import struct
import time
from collections import deque
from html import escape, unescape
from typing import Optional

import aiohttp
import websockets
from dotenv import load_dotenv

load_dotenv(override=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("jin10")

# ─── 配置 ───────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

TIER_LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
TIER_RANK = {level: rank for rank, level in enumerate(TIER_LEVELS, start=1)}

def _resolve_max_tier(raw: str) -> int:
    raw = raw.strip().upper()
    if raw in TIER_RANK:
        return TIER_RANK[raw]
    try:
        return int(raw)
    except ValueError:
        return TIER_RANK["MEDIUM"]

MAX_TIER_TO_SEND = _resolve_max_tier(os.getenv("MAX_TIER_TO_SEND", "MEDIUM"))

WS_URLS = [url.strip() for url in os.getenv("WS_URLS", "wss://wss-flash-2.jin10.com/").split(",") if url.strip()]
WS_RECONNECT_DELAY = float(os.getenv("WS_RECONNECT_DELAY", "5"))
WS_IDLE_TIMEOUT = int(os.getenv("WS_IDLE_TIMEOUT", "180"))

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

DEFAULT_KEYWORDS = [
    # --- 加密貨幣核心資產與概念 ---
    "比特币", "Bitcoin", "BTC", "以太坊", "Ethereum", "ETH",
    "加密货币", "加密貨幣", "数字货币", "虚拟货币", "币圈", "crypto", "cryptocurrency",
    "链上", "on-chain", "DeFi", "NFT", "Web3", "山寨币", "altcoin",
    "Solana", "SOL", "XRP", "Ripple", "狗狗币", "Dogecoin", "DOGE",
    "币安币", "BNB", "Cardano", "ADA", "Polkadot", "Avalanche", "AVAX",
    "Layer2", "L2",

    # --- 交易所與機構生態 ---
    "币安", "Binance", "Coinbase", "OKX", "Bybit", "Kraken", "Bitfinex",
    "火币", "Huobi", "HTX", "灰度", "Grayscale", "贝莱德", "BlackRock",
    "MicroStrategy", "Strategy", "Circle", "Tether", "USDT", "USDC", "稳定币",
    "stablecoin",

    # --- ETF 與監管 ---
    "现货ETF", "比特币ETF", "以太坊ETF", "SEC", "CFTC", "证监会", "香港证监会",
    "监管", "稳定币法案", "GENIUS Act",

    # --- 市場動態與風險事件 ---
    "爆仓", "清算", "做多", "做空", "杠杆", "减半", "halving",
    "黑客", "被盗", "交易所停摆", "挤兑", "脱锚", "depeg", "崩盘", "暴跌", "暴涨",

    # --- 關鍵人物 ---
    "特朗普", "Trump", "马斯克", "Musk", "鲍威尔", "Powell",
    "赵长鹏", "CZ", "Saylor", "Michael Saylor", "Vitalik", "Buterin",

    # --- 宏觀驅動（僅保留會直接牽動加密貨幣波動的核心因子） ---
    "美联储", "Fed", "FOMC", "CPI", "PCE", "非农", "通胀", "降息", "加息", "利率",
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
GEMINI_PROMPT = """You are Jarvis, an elite AI advisor to Sir, specializing in cryptocurrency market intelligence. Your objective is to (1) grade how much this news flash is likely to move the crypto market, and (2) if it's worth surfacing, produce a dense, refined briefing.

Analyze the provided news flash below and respond according to the rules.

# News flash:
{text}

# Step 1 — Tier Classification (crypto market impact):
- CRITICAL (最高): 直接且立即決定 BTC/ETH 等主流幣種短時間內大幅波動的重大事件。例如：Fed利率決議、比特幣/以太坊現貨ETF獲批或遭拒、SEC對主要交易所或機構的重大監管行動、大型交易所/機構爆雷或破產、重大駭客攻擊、貝萊德等巨頭大額增減持、穩定幣脫錨。
- HIGH (高): 對加密貨幣市場有明顯但非決定性影響。例如：CPI/非農等宏觀數據、Fed官員鷹鴿表態、大型機構ETF資金流向、大額鏈上轉帳或巨鯨動向、主要國家監管政策變化、Trump/Musk等關鍵人物涉及crypto的言論。
- MEDIUM (中): 與crypto有一定關聯但影響有限。例如：單一項目或協議更新、中小型交易所動態、非主流代幣價格波動、行業報告。
- LOW (低/幾乎不相關): 幾乎與加密貨幣市場無實質關聯的新聞（即使字面上出現了關鍵詞）。

Set "relevant" to false ONLY if the news has no meaningful connection to the crypto market at all (tier should then also be LOW).

# Step 2 — Briefing (only meaningful if tier is CRITICAL, HIGH, or MEDIUM; otherwise you may leave "message" short):
Write "message" as an HTML-formatted briefing in Traditional Chinese following these rules:
1. Persona: Professional, sharp, elegant, and understatedly loyal. Zero Fluff — no greetings or filler.
2. Primary Language: Traditional Chinese (絕對不能出現簡體中文).
3. Keep STRICTLY in English without translation: geopolitical/location names (US, Israel, Ukraine, Taiwan, EU), financial institutions & key entities (Fed, OPEC, SEC, BRK, Trump), tech/crypto/macro terms (Layer 2, Liquidity, FVG, CPI, PCE, Bullish). Do NOT append Chinese translations after English terms.
4. Do NOT output「中國台灣」, always use「台灣」.
5. Only standard HTML bold tags (<b>...</b>) and italic tags (<i>...</i>) and <code>...</code> are allowed inside "message". Do NOT output any other HTML tags, and do NOT use Markdown.

Output structure for the "message" field (use \\n for line breaks):
<b>(News title)</b>

(簡單用一句話總結新聞)

<b>Crypto (Short-term)</b>
(短線 Analysis，用簡單的方式精簡說明)

<b>總體經濟影響</b>
(除非影響極大則用「一句話簡單說明」不然全部省略)

<b>世界發展影響</b>
(除非影響極大則用「一句話簡單說明」不然全部省略)

<b>Keywords</b> | <code>Term A</code>, <code>Term B</code>, <code>Term C</code>

# Output format:
Respond with ONLY a raw JSON object (no markdown fences, no commentary) matching this shape:
{{"tier": <"CRITICAL"|"HIGH"|"MEDIUM"|"LOW">, "relevant": <true|false>, "message": "<the HTML briefing string, or a short reason if not relevant>"}}
"""

async def summarize_with_gemini(session: aiohttp.ClientSession, text: str) -> Optional[dict]:
    """呼叫 Gemini 取得分級與摘要。回傳 {"tier": int, "relevant": bool, "message": str}，失敗回傳 None。"""
    if not GEMINI_API_KEY:
        return None
    url = GEMINI_URL.format(model=GEMINI_MODEL)

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY
    }

    payload = {
        "contents": [{"parts": [{"text": GEMINI_PROMPT.format(text=text)}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "tier": {"type": "STRING", "enum": TIER_LEVELS},
                    "relevant": {"type": "BOOLEAN"},
                    "message": {"type": "STRING"},
                },
                "required": ["tier", "relevant", "message"],
            },
        },
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
                return None
            data = await resp.json()
            candidates = data.get("candidates") or []
            if not candidates:
                return None
            parts = candidates[0].get("content", {}).get("parts", [])
            raw_text = "".join(p.get("text", "") for p in parts).strip()
            if not raw_text:
                return None
            try:
                result = json.loads(raw_text)
            except json.JSONDecodeError:
                log.warning("Gemini 回傳非合法 JSON：%s", raw_text[:300])
                return None
            tier = str(result.get("tier") or "").strip().upper()
            if tier not in TIER_RANK:
                tier = None
            return {
                "tier": tier,
                "relevant": bool(result.get("relevant", True)),
                "message": str(result.get("message", "")).strip(),
            }
    except Exception as exc:
        log.warning("Gemini 呼叫異常：%s", exc)
        return None


# ─── 近期快訊上下文（供問答使用） ────────────────────────────────────────────

CONTEXT_MAX_ITEMS = int(os.getenv("CONTEXT_MAX_ITEMS", "80"))
CONTEXT_MAX_AGE_SEC = int(os.getenv("CONTEXT_MAX_AGE_SEC", str(6 * 3600)))  # 預設保留 6 小時

recent_news: deque[dict] = deque(maxlen=CONTEXT_MAX_ITEMS)

def remember_news(title: str, content: str, tier: Optional[str]) -> None:
    now = time.time()
    recent_news.append({"ts": now, "title": title, "content": content, "tier": tier})
    while recent_news and now - recent_news[0]["ts"] > CONTEXT_MAX_AGE_SEC:
        recent_news.popleft()

def build_context_snippet(limit: int = 40) -> str:
    items = list(recent_news)[-limit:]
    if not items:
        return "（目前沒有近期快訊紀錄）"
    lines = []
    for it in items:
        clock = time.strftime("%H:%M", time.localtime(it["ts"]))
        tier = it.get("tier") or "-"
        head = (it["title"] or it["content"][:60]).strip().replace("\n", " ")
        lines.append(f"[{clock}] ({tier}) {head}")
    return "\n".join(lines)


# ─── Telegram 問答（Gemini） ─────────────────────────────────────────────────

QA_PROMPT = """You are Jarvis, an elite AI advisor to Sir, specializing in cryptocurrency and macro market intelligence. Sir is asking you a question directly in Telegram — answer it as his trusted analyst.

# 你近期監控到、且已判定與加密貨幣/總經相關的快訊列表（僅供參考背景，時間為系統本地時間，若與問題無關可忽略，不要虛構列表中沒有的具體數字）：
{context}

# Sir 的問題：
{question}

# 回覆規則：
1. Persona：專業、犀利、內斂而忠誠，零廢話，不要有問候語或客套語。
2. 主要語言：繁體中文（絕對不能出現簡體中文）。
3. 以下詞彙一律保留英文原文，不要附加中文翻譯：地緣政治/地名（US, Israel, Ukraine, Taiwan, EU）、金融機構與關鍵實體（Fed, OPEC, SEC, BRK, Trump）、科技/加密/總經術語（Layer 2, Liquidity, FVG, CPI, PCE, Bullish）。
4. 不要輸出「中國台灣」，一律使用「台灣」。
5. 只能使用 HTML 的 <b>...</b>、<i>...</i>、<code>...</code> 標籤，不要使用任何其他 HTML 標籤，也不要使用 Markdown（例如 ** 或 #）。
6. 回答要有觀點、精簡扼要，直接切入重點；若上面的快訊列表不足以回答，可依你自身的總經/地緣政治/市場知識合理分析，但要清楚區分「已知快訊」與「你的推論判斷」。
7. 直接輸出最終要傳給 Sir 的訊息內容即可，不要輸出 JSON、不要加前綴說明。
"""

async def ask_gemini_qa(session: aiohttp.ClientSession, question: str) -> Optional[str]:
    if not GEMINI_API_KEY:
        return None
    url = GEMINI_URL.format(model=GEMINI_MODEL)
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }
    prompt = QA_PROMPT.format(context=build_context_snippet(), question=question)
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        async with session.post(
            url,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                log.warning("Gemini 問答呼叫失敗：status=%s body=%s", resp.status, body[:300])
                return None
            data = await resp.json()
            candidates = data.get("candidates") or []
            if not candidates:
                return None
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts).strip()
            return text or None
    except Exception as exc:
        log.warning("Gemini 問答呼叫異常：%s", exc)
        return None


# ─── Telegram 推播 ──────────────────────────────────────────────────────────

async def send_telegram(session: aiohttp.ClientSession, text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram 未配置，略過發送：\n%s", text)
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
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

TIER_BADGES = {"CRITICAL": "CRITICAL", "HIGH": "HIGH", "MEDIUM": "MEDIUM"}

def format_message(title: str, content: str, summary: str, tier: Optional[str] = None) -> str:
    parts = []
    badge = TIER_BADGES.get(tier)
    if badge:
        parts.append(badge)
    if summary:
        parts.append(f"{(summary)}")
    ## if content:
        ## parts.append(f"\n<b>Source</b>\n{escape(content)}")
    return "\n".join(parts) if parts else ""


# ─── 主流程 ─────────────────────────────────────────────────────────────────

async def handle_item(session: aiohttp.ClientSession, item: dict) -> None:
    title, content = item_text(item)
    full_text = f"{title} {content}".strip()
    if not full_text:
        return
    if not match_keywords(full_text):
        return

    log.info("命中關鍵詞：%s", (title or content)[:60])

    tier: Optional[str] = None
    summary = ""
    if GEMINI_API_KEY:
        result = await summarize_with_gemini(session, full_text)
        if result is None:
            # Gemini 呼叫失敗，不做分級過濾，直接以原始標題/內容推播（保底行為）
            log.warning("Gemini 分級失敗，略過分級直接推播：%s", (title or content)[:60])
            remember_news(title, content, None)
        else:
            tier = result["tier"]
            remember_news(title, content, tier)
            tier_rank = TIER_RANK.get(tier)
            if not result["relevant"] or (tier_rank is not None and tier_rank > MAX_TIER_TO_SEND):
                log.info("Gemini 判定 tier=%s relevant=%s，略過推送：%s",
                          tier, result["relevant"], (title or content)[:60])
                return
            summary = result["message"]
    else:
        remember_news(title, content, None)

    msg = format_message(title, content, summary, tier=tier)
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

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

async def get_bot_username(session: aiohttp.ClientSession) -> str:
    try:
        async with session.get(f"{TELEGRAM_API}/getMe", timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()
            return (data.get("result") or {}).get("username", "")
    except Exception as exc:
        log.warning("取得 Bot 資訊失敗：%s", exc)
        return ""

def extract_question(text: str, bot_username: str, chat_type: str) -> Optional[str]:
    """判斷這則訊息是不是要問 AI 助手的問題，是的話回傳去除 mention/指令後的問題內容。"""
    text = (text or "").strip()
    if not text or text.startswith("/start") or text.startswith("/help"):
        return None

    if bot_username:
        mention = f"@{bot_username}"
        idx = text.lower().find(mention.lower())
        if idx != -1:
            question = (text[:idx] + text[idx + len(mention):]).strip()
            return question or None

    if text.startswith("/ask"):
        question = text[len("/ask"):].strip()
        return question or None

    # 私訊聊天視為直接對話，不需要 @mention
    if chat_type == "private":
        return text

    return None

async def send_telegram_reply(
    session: aiohttp.ClientSession,
    chat_id: str,
    text: str,
    reply_to: Optional[int] = None,
) -> bool:
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to

    for attempt in range(1, 3):
        try:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return True
                body = await resp.text()
                log.warning("Telegram 回覆失敗：status=%s attempt=%s body=%s", resp.status, attempt, body[:300])
                if resp.status == 400:
                    # 可能是 Gemini 輸出了不合法的 HTML，退回純文字重試一次
                    fallback = dict(payload)
                    fallback.pop("parse_mode", None)
                    async with session.post(url, json=fallback, timeout=aiohttp.ClientTimeout(total=15)) as resp2:
                        if resp2.status == 200:
                            return True
        except Exception as exc:
            log.warning("Telegram 回覆異常：attempt=%s error=%s", attempt, exc)
        await asyncio.sleep(1.5)
    return False

async def telegram_qa_loop(session: aiohttp.ClientSession) -> None:
    if not TELEGRAM_BOT_TOKEN:
        log.warning("未設置 TELEGRAM_BOT_TOKEN，跳過問答監聽")
        return

    bot_username = await get_bot_username(session)
    if bot_username:
        log.info("Telegram 問答監聽已啟動，Bot 帳號：@%s", bot_username)
    else:
        log.info("Telegram 問答監聽已啟動（未取得 bot username，群組中請改用 /ask 指令）")

    url = f"{TELEGRAM_API}/getUpdates"
    offset: Optional[int] = None

    while True:
        params = {"timeout": 30}
        if offset is not None:
            params["offset"] = offset
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=40)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    log.warning("getUpdates 失敗：status=%s body=%s", resp.status, body[:300])
                    await asyncio.sleep(5)
                    continue
                data = await resp.json()
        except Exception as exc:
            log.warning("getUpdates 異常：%s", exc)
            await asyncio.sleep(5)
            continue

        for update in data.get("result", []):
            offset = update["update_id"] + 1
            message = update.get("message") or update.get("edited_message") or {}
            chat = message.get("chat", {})
            chat_id = str(chat.get("id", ""))
            chat_type = str(chat.get("type", ""))
            text = message.get("text") or ""
            message_id = message.get("message_id")

            if TELEGRAM_CHAT_ID and chat_id != str(TELEGRAM_CHAT_ID):
                continue

            question = extract_question(text, bot_username, chat_type)
            if not question:
                continue

            log.info("收到問答請求：%s", question[:60])
            answer = await ask_gemini_qa(session, question)
            if not answer:
                answer = "暫時無法產生回覆，請稍後再試一次。"
            ok = await send_telegram_reply(session, chat_id, answer, reply_to=message_id)
            log.info("問答回覆%s", "成功" if ok else "失敗")


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

        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            log.warning("未設置 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID，Telegram 推播與問答會被跳過")

        await asyncio.gather(
            ws_loop(session),
            telegram_qa_loop(session),
        )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("已手動停止")
