"""Bounded production grounding check using the YouTube owner's request ledger."""

import asyncio

import aiohttp

from gemini import GEMINI_MODEL, GEMINI_SEARCH_MODEL, call_gemini


async def main() -> None:
    async with aiohttp.ClientSession() as session:
        text = await call_gemini(
            session,
            "Use Google Search to find the official Ethereum documentation. "
            "In one sentence explain what Ethereum is and cite the official source.",
            google_search=True, usage_scope="youtube", timeout=90,
        )
    print("Video model:", GEMINI_MODEL)
    print("Search model:", GEMINI_SEARCH_MODEL)
    if not text:
        raise RuntimeError("Grounded search probe did not return validated citations")
    print("Grounded search with validated citations: successful")


if __name__ == "__main__":
    asyncio.run(main())
