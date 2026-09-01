import asyncio
import os
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def mask_key(key: str) -> str:
    if not key:
        return "(Not set)"
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}...{key[-4:]} (length {len(key)})"


async def main() -> None:
    print("=" * 60)
    print(f"GEMINI_MODEL   : {GEMINI_MODEL}")
    print(f"GEMINI_API_KEY : {mask_key(GEMINI_API_KEY)}")
    print("=" * 60)

    if not GEMINI_API_KEY:
        print("[ERROR] GEMINI_API_KEY is not set. Please check your .env file or environment variables.")
        return

    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    payload = {"contents": [{"parts": [{"text": "Please reply with exactly two characters: OK"}]}]}

    print("[INFO] Sending test request...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                GEMINI_URL,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                body = await resp.text()
                if resp.status != 200:
                    print(f"[ERROR] Request failed: status={resp.status}")
                    print(body[:1000])
                    print(
                        "\nCommon causes: invalid or deleted API key (401), "
                        "incorrect GEMINI_MODEL or missing model access for the account (404), "
                        "quota exhausted (429)."
                    )
                    return
                data = await resp.json()
    except Exception as exc:
        print(f"[ERROR] Request error: {exc}")
        return

    candidates = data.get("candidates") or []
    if not candidates:
        print("[ERROR] No candidates were returned in the response. Raw response:")
        print(data)
        return

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()

    print(f"[INFO] Gemini response: {text}")
    print("[OK] The API key is working correctly.")


if __name__ == "__main__":
    asyncio.run(main())

"""
echo $env:GEMINI_API_KEY 
remove-item env:GEMINI_API_KEY
"""