import asyncio
import json
import os
import re
from typing import Optional

import aiohttp

from common import get_logger

TELEGRAM_BOT_TOKEN_01 = os.getenv("TELEGRAM_BOT_TOKEN_01", "")
TELEGRAM_BOT_TOKEN_02 = os.getenv("TELEGRAM_BOT_TOKEN_02", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN_01}"

log = get_logger("telegram")


def _strip_html_tags(text: str) -> str:
    """Fallback for when Telegram rejects a message due to malformed HTML (400):
    strip the tags instead of sending them as literal text to the chat."""
    return re.sub(r"<[^>]+>", "", text)


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

    url = f"{TELEGRAM_API}/sendMessage"
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
                    await asyncio.sleep(retry_after)
                    continue
        except Exception as exc:
            log.warning("Telegram send error: attempt=%s error=%s", attempt, exc)
        await asyncio.sleep(1.5)
    return False


async def get_bot_username(session: aiohttp.ClientSession) -> str:
    try:
        async with session.get(f"{TELEGRAM_API}/getMe", timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()
            return (data.get("result") or {}).get("username", "")
    except Exception as exc:
        log.warning("Failed to fetch bot information: %s", exc)
        return ""