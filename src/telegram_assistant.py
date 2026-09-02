import asyncio
import os
import time
from typing import Optional

import aiohttp

from common import get_logger, load_recent_news
from gemini import GEMINI_API_KEY, call_gemini
from tg import (
    TELEGRAM_API,
    TELEGRAM_BOT_TOKEN_01,
    TELEGRAM_CHAT_ID,
    get_bot_username,
    send_telegram_message,
)

log = get_logger("jin10-qa")

CONTEXT_SNIPPET_LIMIT = int(os.getenv("CONTEXT_SNIPPET_LIMIT", "40"))


# ─── Recent flash context (read from the shared file written by jin10_monitor.py) ────────────────────

def build_context_snippet(limit: int = CONTEXT_SNIPPET_LIMIT) -> str:
    items = load_recent_news()[-limit:]
    if not items:
        return "(There is no recent flash-news record at the moment)"
    lines = []
    for it in items:
        clock = time.strftime("%H:%M", time.localtime(it["ts"]))
        tier = it.get("tier") or "-"
        title = it.get("title") or ""
        content = it.get("content") or ""
        head = (title or content[:60]).strip().replace("\n", " ")
        lines.append(f"[{clock}] ({tier}) {head}")
    return "\n".join(lines)


# ─── Telegram Q&A (Gemini) ────────────────────────────────────────────────────

QA_PROMPT = """You are Jarvis, an elite AI advisor to Sir, specializing in cryptocurrency and macro market intelligence. Sir is asking you a question directly in Telegram — answer it as his trusted analyst.

# The list of recent flash updates you have monitored and judged to be relevant to crypto/macroeconomics (for background only; times are in local system time. If a message is unrelated to the question, ignore it. Do not invent concrete figures that are not in the list):
{context}

# Sir's question:
{question}

# Response rules:
1. Persona: professional, sharp, restrained, and loyal. Zero fluff; no greetings or pleasantries.
2. Primary language: Traditional Chinese (no simplified Chinese at all).
3. Keep the following terms in their original English form without adding Chinese translations: geopolitical/place names (US, Israel, Ukraine, Taiwan, EU), financial institutions and key entities (Fed, OPEC, SEC, BRK, Trump), and technology/crypto/macro terms (Layer 2, Liquidity, FVG, CPI, PCE, Bullish).
4. Do NOT output "中國台灣"; always use "台灣".
5. Only use HTML tags <b>...</b>, <i>...</i>, and <code>...</code>. Do not use any other HTML tags or Markdown (for example, ** or #).
6. The answer should be opinionated, concise, and direct; get to the core point immediately. If the flash list above is insufficient to answer the question, you may apply your own macro/geopolitical/market knowledge, but clearly separate "known flash updates" from "your inference and judgment".
7. Output only the final message to send to Sir. Do not output JSON or add any prefix or explanation.
"""

async def ask_gemini_qa(session: aiohttp.ClientSession, question: str) -> Optional[str]:
    prompt = QA_PROMPT.format(context=build_context_snippet(), question=question)
    return await call_gemini(session, prompt, timeout=30)


# ─── Telegram getUpdates ─────────────────────────────────────────────────────

def extract_question(text: str, bot_username: str, chat_type: str) -> Optional[str]:
    """Determine whether the message is a question for the AI assistant; if so, return the question text without the mention or command."""
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

    # Private chats are treated as direct conversations, so no @mention is required
    if chat_type == "private":
        return text

    return None


# ─── Main loop ─────────────────────────────────────────────────────────────────

async def telegram_assistant_loop(session: aiohttp.ClientSession) -> None:
    bot_username = await get_bot_username(session)
    if bot_username:
        log.info("Telegram Assistant listener started. Bot username: @%s", bot_username)
    else:
        log.info("Telegram Assistant listener started (bot username not available; in groups, use the /ask command)")

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
                    log.warning("getUpdates failed: status=%s body=%s", resp.status, body[:300])
                    await asyncio.sleep(5)
                    continue
                data = await resp.json()
        except Exception as exc:
            log.warning("getUpdates error: %s", exc)
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

            log.info("Received Q&A request: %s", question[:60])
            if not GEMINI_API_KEY:
                answer = "GEMINI_API_KEY is not set, so the Q&A feature is currently unavailable."
            else:
                answer = await ask_gemini_qa(session, question) or "The response could not be generated temporarily. Please try again later."
            ok = await send_telegram_message(session, chat_id, answer, reply_to=message_id)
            log.info("Q&A response %s", "successful" if ok else "failed")


async def main() -> None:
    if not TELEGRAM_BOT_TOKEN_01:
        log.error("TELEGRAM_BOT_TOKEN_01 is not set; the Q&A service cannot start")
        return
    if not GEMINI_API_KEY:
        log.warning("GEMINI_API_KEY is not set; Q&A will always return a failure message")

    async with aiohttp.ClientSession() as session:
        await telegram_assistant_loop(session)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Stopped manually")