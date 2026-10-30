"""Run ingestion and Telegram Q&A against the same live news files."""

import asyncio
import argparse
import logging

import jin10_monitor
import telegram_assistant
import event_briefing
import delivered_flashes

log = logging.getLogger(__name__)


async def main(*, run_seconds: float | None = None) -> None:
    delivered_flashes.initialize()
    tasks = [
        asyncio.create_task(jin10_monitor.main()),
        asyncio.create_task(telegram_assistant.main()),
        asyncio.create_task(event_briefing.main()),
    ]
    try:
        done, _ = await asyncio.wait(
            tasks, timeout=run_seconds, return_when=asyncio.FIRST_COMPLETED,
        )
        if not done:
            log.info("Scheduled runtime reached; shutting down service components")
            return
        for task in done:
            task.result()
        raise RuntimeError("A flash service component stopped unexpectedly")
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-seconds", type=float, default=None)
    args = parser.parse_args()
    if args.run_seconds is not None and not (0 < args.run_seconds < float("inf")):
        parser.error("--run-seconds must be finite and positive")
    try:
        asyncio.run(main(run_seconds=args.run_seconds))
    except KeyboardInterrupt:
        pass
