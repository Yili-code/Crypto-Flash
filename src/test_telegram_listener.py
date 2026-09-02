import asyncio
import os
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

TELEGRAM_BOT_TOKEN_01 = os.getenv("TELEGRAM_BOT_TOKEN_01", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN_01}"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "")
GITHUB_WORKFLOW_FILE = os.getenv("GITHUB_WORKFLOW_FILE", "telegram_assistant.yml")


async def check_webhook(session: aiohttp.ClientSession) -> None:
    print("=" * 64)
    print("[1] Webhook Status")
    try:
        async with session.get(f"{TELEGRAM_API}/getWebhookInfo", timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()
    except Exception as exc:
        print(f"⚠️  Query failed: {exc}")
        return

    result = data.get("result", {}) if isinstance(data, dict) else {}
    url = result.get("url", "")
    if url:
        print(f"⚠️  Webhook configured: {url}")
        print("    With webhook enabled, getUpdates will conflict.")
        print("    To use long-polling, call deleteWebhook first:")
        print(f"    {TELEGRAM_API}/deleteWebhook")
    else:
        print("✅ No webhook configured. Long-polling should work normally.")

    if result.get("pending_update_count"):
        print(f"    Pending updates: {result['pending_update_count']}")
    if result.get("last_error_message"):
        print(f"    Last error: {result['last_error_message']} ({result.get('last_error_date', '')})")
    print("")


async def check_polling_conflict(session: aiohttp.ClientSession) -> None:
    print("=" * 64)
    print("[2] Real-time getUpdates Check (timeout=1)")
    try:
        async with session.get(
            f"{TELEGRAM_API}/getUpdates",
            params={"timeout": 1},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            body = await resp.json()
    except Exception as exc:
        print(f"⚠️  Request failed: {exc}")
        return

    if resp.status == 409:
        print(f"❌ 409 Conflict: {body.get('description', '')}")
        print("    Another process is currently polling getUpdates.")
        print("    Check: local telegram_assistant.py instance or running GitHub Actions job.")
    elif resp.status == 200:
        print("✅ No conflict detected at this moment.")
        print("Note: This is a point-in-time check; run multiple times for intermittent issues.")
    else:
        print(f"⚠️  Unexpected response: status={resp.status} body={body}")
    print("")


async def check_github_actions(session: aiohttp.ClientSession) -> None:
    print("=" * 64)
    print(f"[3] GitHub Actions: {GITHUB_WORKFLOW_FILE}")

    if not GITHUB_TOKEN or not GITHUB_REPOSITORY:
        print("    (Skipped) GITHUB_TOKEN or GITHUB_REPOSITORY not set.")
        print("    Set these in .env to check running workflow jobs.")
        return

    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/workflows/{GITHUB_WORKFLOW_FILE}/runs"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    try:
        async with session.get(
            url,
            headers=headers,
            params={"status": "in_progress", "per_page": 10},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                print(f"⚠️  Query failed: status={resp.status} body={body[:300]}")
                return
            data = await resp.json()
    except Exception as exc:
        print(f"⚠️  Request error: {exc}")
        return

    runs = data.get("workflow_runs", [])
    if not runs:
        print("✅ No running GitHub Actions jobs.")
        return

    print(f"❌ Found {len(runs)} running job(s), possibly causing conflict:")
    for run in runs:
        print(f"    - Run #{run.get('run_number')} Status={run.get('status')} Started={run.get('run_started_at')}")
        print(f"      {run.get('html_url')}")
    print("")


async def main() -> None:
    if not TELEGRAM_BOT_TOKEN_01:
        print("[ERROR] TELEGRAM_BOT_TOKEN_01 not set in .env or environment.")
        return

    async with aiohttp.ClientSession() as session:
        await check_webhook(session)
        await check_polling_conflict(session)
        await check_github_actions(session)

    print("=" * 64)


if __name__ == "__main__":
    asyncio.run(main())