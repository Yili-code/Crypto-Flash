import asyncio
import json
import os
import re
import time
from typing import Optional

import aiohttp

from common import get_logger

TELEGRAM_BOT_TOKEN_01 = os.getenv("TELEGRAM_BOT_TOKEN_01", "")
TELEGRAM_BOT_TOKEN_02 = os.getenv("TELEGRAM_BOT_TOKEN_02", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN_01}"

# Telegram allows roughly 20 messages/minute to a single group. Bursts of flash news
# used to blow past that and come back as 429 with retry_after in the hundreds of
# seconds, so space sends out instead of discovering the limit the hard way.
SEND_MIN_INTERVAL = float(os.getenv("TELEGRAM_MIN_SEND_INTERVAL", "3.5"))
# Cap on how long a 429 may park the caller. Telegram sometimes asks for 5-10 minutes;
# obeying that inline stalls the jin10 WebSocket receive loop until the server drops it.
MAX_RETRY_AFTER = float(os.getenv("TELEGRAM_MAX_RETRY_AFTER", "30"))

log = get_logger("telegram")

_send_lock = asyncio.Lock()
_last_send_at = 0.0


def _strip_html_tags(text: str) -> str:
    """Fallback for when Telegram rejects a message due to malformed HTML (400):
    strip the tags instead of sending them as literal text to the chat."""
    return re.sub(r"<[^>]+>", "", text)


async def _throttle() -> None:
    """Serialize sends and keep at least SEND_MIN_INTERVAL between them."""
    global _last_send_at
    async with _send_lock:
        wait = SEND_MIN_INTERVAL - (time.monotonic() - _last_send_at)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_send_at = time.monotonic()


async def send_telegram_message(
    session: aiohttp.ClientSession,
    chat_id: str,
    text: str,
    bot_token: Optional[str] = None,
    *,
    reply_to: Optional[int] = None,
    max_attempts: int = 3,
) -> bool:
    token = bot_token or TELEGRAM_BOT_TOKEN_01
    if not token or not chat_id:
        log.warning("Telegram is not configured; skipping send:\n%s", text[:200])
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    base_payload: dict = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_to:
        base_payload["reply_to_message_id"] = reply_to

    use_html = True
    for attempt in range(1, max_attempts + 1):
        if use_html:
            payload = base_payload
        else:
            payload = {k: v for k, v in base_payload.items() if k != "parse_mode"}
            payload["text"] = _strip_html_tags(payload["text"])
        try:
            await _throttle()
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return True
                body = await resp.text()
                log.warning("Telegram send failed: status=%s attempt=%s body=%s", resp.status, attempt, body[:300])

                if resp.status == 400 and use_html:
                    use_html = False
                    continue
                if resp.status == 429:
                    retry_after = 2.0
                    try:
                        retry_after = float(json.loads(body).get("parameters", {}).get("retry_after", 2))
                    except Exception:
                        pass
                    await asyncio.sleep(min(retry_after, MAX_RETRY_AFTER))
                    continue
        except Exception as exc:
            log.warning("Telegram send error: attempt=%s error=%s", attempt, exc)
        await asyncio.sleep(1.5)
    return False


async def check_chat_access(
    session: aiohttp.ClientSession,
    chat_id: str,
    bot_token: Optional[str] = None,
) -> bool:
    """Pre-flight getChat so a misconfigured chat id fails loudly up front, instead of
    after every expensive summarisation has already been paid for."""
    token = bot_token or TELEGRAM_BOT_TOKEN_01
    if not token or not chat_id:
        log.error("Telegram is not configured (missing bot token or chat id)")
        return False
    url = f"https://api.telegram.org/bot{token}/getChat"
    try:
        async with session.get(url, params={"chat_id": chat_id}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()
    except Exception as exc:
        log.warning("Could not verify Telegram chat access: %s", exc)
        return True  # network hiccup, not a configuration error: let the send retry decide
    if data.get("ok"):
        return True
    log.error(
        "Telegram chat %s is unreachable for this bot: %s. "
        "Check TELEGRAM_CHAT_ID and make sure the bot has been added to that chat.",
        chat_id, data.get("description"),
    )
    return False


async def get_bot_username(session: aiohttp.ClientSession) -> str:
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN_01}/getMe"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()
            return (data.get("result") or {}).get("username", "")
    except Exception as exc:
        log.warning("Failed to fetch bot information: %s", exc)
        return ""
