"""Bounded production grounding check using the YouTube owner's request ledger."""

import asyncio
import os
import re

import aiohttp

from gemini import GEMINI_MODEL, GEMINI_SEARCH_MODEL, call_gemini


def safe_probe_error(message: str) -> str:
    # The probe uses only its fixed public prompt; never enable this for user prompts.
    key = os.getenv("GEMINI_API_KEY", "")
    if key:
        message = message.replace(key, "[redacted]")
    message = re.sub(r"https?://\S+", "[url]", message)
    message = re.sub(r"projects/[^/\s]+", "projects/[redacted]", message)
    message = re.sub(r"\b[A-Za-z0-9_-]{25,}\b", "[redacted]", message)
    return " ".join(message.split())[:500]


async def main() -> None:
    trace = aiohttp.TraceConfig()

    async def inspect_error(session, context, params):
        if params.method == "POST" and params.response.status >= 400:
            try:
                data = await params.response.json()
                message = (data.get("error") or {}).get("message", "")
                if isinstance(message, str):
                    print("Fixed public probe error:", safe_probe_error(message))
            except (ValueError, aiohttp.ContentTypeError, AttributeError):
                print("Fixed public probe error: non-JSON error response")

    trace.on_request_end.append(inspect_error)
    async with aiohttp.ClientSession(trace_configs=[trace]) as session:
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
