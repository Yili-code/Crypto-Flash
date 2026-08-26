"""
telegram_qa.py — 獨立的 Telegram 問答服務

從 jin10_monitor.py 拆分出來，專門負責：
1. 輪詢 Telegram getUpdates，判斷訊息是否為要問 AI 的問題
2. 呼叫 Gemini 產生回覆
3. 把回覆送回 Telegram

與 jin10_monitor.py（負責監控 jin10 快訊並推播）是兩個獨立的行程，
可以分開部署 / 分開重啟，互不影響。

兩者透過共用的 JSON 檔（NEWS_CONTEXT_FILE，預設 recent_news.json）交換
「近期快訊」，讓問答時能帶入背景資訊：
- jin10_monitor.py 每次判定完快訊後會把 recent_news 寫進這個檔案
- telegram_qa.py 每次回答問題前會讀取這個檔案組成上下文

如果檔案不存在或已過期（沒有 jin10_monitor.py 同步在跑），仍會照常運作，
只是回答時不會帶有近期快訊背景。
"""

import asyncio
import json
import logging
import os
import time
from typing import Optional

import aiohttp
from dotenv import load_dotenv

load_dotenv(override=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("jin10-qa")

# ─── 配置 ───────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# 與 jin10_monitor.py 共用同一份近期快訊上下文檔（同一路徑 / 同一台機器 / 同一個持久化儲存）
NEWS_CONTEXT_FILE = os.getenv("NEWS_CONTEXT_FILE", "recent_news.json")
CONTEXT_MAX_AGE_SEC = int(os.getenv("CONTEXT_MAX_AGE_SEC", str(6 * 3600)))  # 預設保留 6 小時
CONTEXT_SNIPPET_LIMIT = int(os.getenv("CONTEXT_SNIPPET_LIMIT", "40"))


# ─── 近期快訊上下文（讀取 jin10_monitor.py 寫出的共用檔） ────────────────────

def load_recent_news() -> list[dict]:
    if not os.path.exists(NEWS_CONTEXT_FILE):
        return []
    try:
        with open(NEWS_CONTEXT_FILE, encoding="utf-8") as f:
            items = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("讀取近期快訊上下文檔失敗：%s", exc)
        return []
    if not isinstance(items, list):
        return []
    now = time.time()
    return [it for it in items if isinstance(it, dict) and now - it.get("ts", 0) <= CONTEXT_MAX_AGE_SEC]


def build_context_snippet(limit: int = CONTEXT_SNIPPET_LIMIT) -> str:
    items = load_recent_news()[-limit:]
    if not items:
        return "（目前沒有近期快訊紀錄）"
    lines = []
    for it in items:
        clock = time.strftime("%H:%M", time.localtime(it["ts"]))
        tier = it.get("tier") or "-"
        title = it.get("title") or ""
        content = it.get("content") or ""
        head = (title or content[:60]).strip().replace("\n", " ")
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


# ─── Telegram getMe / getUpdates / sendMessage ─────────────────────────────

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


# ─── 主迴圈 ─────────────────────────────────────────────────────────────────

async def telegram_qa_loop(session: aiohttp.ClientSession) -> None:
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


async def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        log.error("未設置 TELEGRAM_BOT_TOKEN，無法啟動問答服務")
        return
    if not GEMINI_API_KEY:
        log.warning("未設置 GEMINI_API_KEY，問答將永遠回覆失敗訊息")

    async with aiohttp.ClientSession() as session:
        await telegram_qa_loop(session)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("已手動停止")