"""One-tap Telegram commands; parameterized commands remain available via help."""

import asyncio

import aiohttp

from common import get_logger
from tg import TELEGRAM_API, TELEGRAM_BOT_TOKEN_01

log = get_logger("telegram-menu")
MENU_COMMANDS = [
    {"command": name, "description": description}
    for name, description in (
        ("news", "最近快訊"),
        ("important", "重要快訊摘要"),
        ("digest", "昨日重點整理"),
        ("tracks", "追蹤清單與未讀筆數"),
        ("updates", "追蹤主題最新進展"),
        ("status", "新聞資料狀態"),
        ("help", "完整指令與使用說明"),
    )
]


async def sync_command_menu(session: aiohttp.ClientSession) -> bool:
    if not TELEGRAM_BOT_TOKEN_01:
        return False
    try:
        async with session.post(
            f"{TELEGRAM_API}/setMyCommands",
            json={"commands": MENU_COMMANDS},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as response:
            result = await response.json()
            ok = response.status == 200 and result.get("ok") is True
            if not ok:
                log.warning("Command menu update rejected (status=%s)", response.status)
            return ok
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        log.warning("Command menu update unavailable")
        return False


async def main() -> None:
    async with aiohttp.ClientSession() as session:
        if not await sync_command_menu(session):
            raise SystemExit("Command menu update failed")
        print("Command menu updated")


if __name__ == "__main__":
    asyncio.run(main())
