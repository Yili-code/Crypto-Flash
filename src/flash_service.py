"""Run ingestion and Telegram Q&A against the same live news files."""

import asyncio

import jin10_monitor
import telegram_assistant
import event_briefing
import delivered_flashes


async def main() -> None:
    delivered_flashes.initialize()
    tasks = [
        asyncio.create_task(jin10_monitor.main()),
        asyncio.create_task(telegram_assistant.main()),
        asyncio.create_task(event_briefing.main()),
    ]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
        raise RuntimeError("A flash service component stopped unexpectedly")
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
