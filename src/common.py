import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import aiohttp
from dotenv import load_dotenv

# ─── 路徑 ───────────────────────────────────────────────────────────────────
# 不論從專案根目錄或 src/ 底下執行，都以本檔案所在目錄的上一層作為專案根目錄，
# 確保 .env / data/recent_news.json 的路徑不受目前工作目錄影響。
BASE_DIR = Path(__file__).resolve().parent.parent

# 注意：override 預設為 False（不覆寫既有環境變數）。
# 這樣在 GitHub Actions 等以 Secrets 注入環境變數的情境下，.env（若被誤帶進 repo）
# 不會反過來蓋掉正式的環境變數；本機開發時沒有設定環境變數，才會吃到 .env 的值。
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


_log = get_logger("common")

# ─── Telegram / Gemini 基本設定 ─────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# ─── Tier 分級 ──────────────────────────────────────────────────────────────

TIER_LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
TIER_RANK = {level: rank for rank, level in enumerate(TIER_LEVELS, start=1)}


def resolve_max_tier(raw: str) -> int:
    raw = raw.strip().upper()
    if raw in TIER_RANK:
        return TIER_RANK[raw]
    try:
        return int(raw)
    except ValueError:
        return TIER_RANK["MEDIUM"]


MAX_TIER_TO_SEND = resolve_max_tier(os.getenv("MAX_TIER_TO_SEND", "MEDIUM"))

# ─── 近期快訊上下文（monitor 寫入、qa 讀取，共用同一份存取邏輯避免格式漂移）──

NEWS_CONTEXT_FILE = Path(os.getenv("NEWS_CONTEXT_FILE", str(BASE_DIR / "data" / "recent_news.json")))
CONTEXT_MAX_ITEMS = int(os.getenv("CONTEXT_MAX_ITEMS", "80"))
CONTEXT_MAX_AGE_SEC = int(os.getenv("CONTEXT_MAX_AGE_SEC", str(6 * 3600)))  # 預設保留 6 小時


def load_recent_news() -> list[dict]:
    if not NEWS_CONTEXT_FILE.exists():
        return []
    try:
        items = json.loads(NEWS_CONTEXT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _log.warning("讀取近期快訊上下文檔失敗：%s", exc)
        return []
    if not isinstance(items, list):
        return []
    now = time.time()
    return [it for it in items if isinstance(it, dict) and now - it.get("ts", 0) <= CONTEXT_MAX_AGE_SEC]


def save_recent_news(items: list[dict]) -> None:
    try:
        NEWS_CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = NEWS_CONTEXT_FILE.with_suffix(NEWS_CONTEXT_FILE.suffix + ".tmp")
        tmp_path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(NEWS_CONTEXT_FILE)
    except OSError as exc:
        _log.warning("寫入近期快訊上下文檔失敗：%s", exc)


# ─── Gemini 呼叫（共用） ─────────────────────────────────────────────────────

async def call_gemini(
    session: aiohttp.ClientSession,
    prompt: str,
    *,
    response_schema: Optional[dict] = None,
    timeout: int = 20,
) -> Optional[str]:
    """呼叫 Gemini generateContent，回傳原始文字內容；未設定金鑰或失敗回傳 None。"""
    log = get_logger("gemini")
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
    log = get_logger("gemini")
    if not GEMINI_API_KEY:
        log.warning("未設置 GEMINI_API_KEY")
        return False
    text = await call_gemini(session, "Ping", timeout=10)
    if text is not None:
        log.info("Gemini API Key 驗證成功！連線正常。")
        return True
    log.error("Gemini API Key 驗證失敗，請檢查 GEMINI_API_KEY / GEMINI_MODEL。")
    return False


# ─── Telegram 發送（共用，含 400 錯誤時去除 parse_mode 的保底重試、429 backoff）──

async def send_telegram_message(
    session: aiohttp.ClientSession,
    chat_id: str,
    text: str,
    *,
    reply_to: Optional[int] = None,
    max_attempts: int = 3,
) -> bool:
    log = get_logger("telegram")
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        log.warning("Telegram 未配置，略過發送：\n%s", text[:200])
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
        payload = base_payload if use_html else {k: v for k, v in base_payload.items() if k != "parse_mode"}
        try:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return True
                body = await resp.text()
                log.warning("Telegram 發送失敗：status=%s attempt=%s body=%s", resp.status, attempt, body[:300])

                if resp.status == 400 and use_html:
                    # 很可能是 Gemini 輸出了不合法的 HTML，之後改用純文字重試，避免每次都重蹈覆轍
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
            log.warning("Telegram 發送異常：attempt=%s error=%s", attempt, exc)
        await asyncio.sleep(1.5)
    return False