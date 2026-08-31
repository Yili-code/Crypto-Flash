import os
from typing import Optional

import aiohttp

from common import get_logger

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

log = get_logger("gemini")


async def call_gemini(
    session: aiohttp.ClientSession,
    prompt: str,
    *,
    response_schema: Optional[dict] = None,
    timeout: int = 20,
) -> Optional[str]:
    if not GEMINI_API_KEY:
        return None
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    payload: dict = {"contents": [{"parts": [{"text": prompt}]}]}
    if response_schema is not None:
        payload["generationConfig"] = {
            "responseMimeType": "application/json",
            "responseSchema": response_schema,
        }
    try:
        async with session.post(
            GEMINI_URL,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=timeout),
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
            text = "".join(p.get("text", "") for p in parts).strip()
            return text or None
    except Exception as exc:
        log.warning("Gemini 呼叫異常：%s", exc)
        return None


async def test_gemini_connection(session: aiohttp.ClientSession) -> bool:
    if not GEMINI_API_KEY:
        log.warning("GEMINI_API_KEY is not set")
        return False
    text = await call_gemini(session, "Ping", timeout=10)
    if text is not None:
        log.info("Gemini API key verified successfully! Connection is working.")
        return True
    log.error("Gemini API key verification failed. Please check GEMINI_API_KEY and GEMINI_MODEL")
    return False