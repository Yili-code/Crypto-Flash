import asyncio
import json
import os
from html import escape
from typing import Optional

import aiohttp

from common import get_logger
import gemini_policy as policy

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "").strip() or "gemini-3.5-flash-lite"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

log = get_logger("gemini")
_scope_locks = {}


async def call_gemini(session, prompt: str, *, usage_scope: str = "live", **kwargs) -> Optional[str]:
    """Serialize each scope so failures cannot race with new budget reservations."""
    loop = asyncio.get_running_loop()
    previous = _scope_locks.get(usage_scope)
    if previous is None or previous[0] is not loop:
        previous = (loop, asyncio.Lock())
        _scope_locks[usage_scope] = previous
    async with previous[1]:
        try:
            return await _call_gemini(session, prompt, usage_scope=usage_scope, **kwargs)
        except policy.PolicyStateError as exc:
            log.error("Gemini usage guard: %s", exc)
            return None

def mask_key(key: str) -> str:
    if not key:
        return "(Not set)"
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}...{key[-4:]} (length {len(key)})"

async def _call_gemini(
    session: aiohttp.ClientSession,
    prompt: str,
    *,
    response_schema: Optional[dict] = None,
    timeout: int = 20,
    google_search: bool = False,
    usage_scope: str = "live",
    **kwargs,
) -> Optional[str]:
    if not GEMINI_API_KEY:
        return None
    
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}

    # 01 -> parts (prompt & extra_parts)
    parts = [{"text": prompt}]
    extra_parts = kwargs.get("extra_parts")
    if extra_parts and isinstance(extra_parts, list):
        parts.extend(extra_parts)

    payload: dict = {"contents": [{"parts": parts}]}
    if google_search:
        payload["tools"] = [{"google_search": {}}]

    # 02 -> system instruction
    system_instruction = kwargs.get("system_instruction")
    if system_instruction:
        payload["system_instruction"] = {
            "parts": [{"text": system_instruction}]
        }

    # 03 -> schema & generation config
    if response_schema is not None:
        payload["generationConfig"] = {
            "responseMimeType": "application/json",
            "responseSchema": response_schema,
        }

    request_id = policy.fingerprint(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    config_id = policy.fingerprint(GEMINI_API_KEY + ":" + GEMINI_MODEL + ":" + os.getenv("GEMINI_POLICY_REVISION", ""))
    reason = policy.reserve(usage_scope, config_id, request_id)
    if reason:
        log.info("Gemini [%s] request deferred: %s", usage_scope, reason)
        return None

    try:
        async with session.post(
            GEMINI_URL,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status != 200:
                try:
                    error_data = await resp.json()
                except (ValueError, aiohttp.ContentTypeError):
                    error_data = {}
                category, delay = policy.classify(resp.status, error_data if isinstance(error_data, dict) else {},
                                                  getattr(resp, "headers", {}))
                policy.failed(usage_scope, category, request_id, delay)
                log.warning("Gemini [%s] HTTP %s: %s", usage_scope, resp.status, category)
                return None
            
            data = await resp.json()
            candidates = data.get("candidates") or []
            if not candidates:
                policy.failed(usage_scope, "empty_response", request_id)
                return None
            if candidates[0].get("finishReason") not in (None, "STOP"):
                policy.failed(usage_scope, "incomplete_response", request_id)
                return None
            
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
            if google_search:
                text = grounded_text(text, candidates[0].get("groundingMetadata") or {})
            if not text:
                policy.failed(usage_scope, "missing_sources" if google_search else "empty_response", request_id)
                return None
            policy.succeeded(usage_scope)
            return text
        
    except policy.PolicyStateError:
        raise
    except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
        category = "timeout" if isinstance(exc, asyncio.TimeoutError) else "network"
        policy.failed(usage_scope, category, request_id)
        log.warning("Gemini [%s]: %s", usage_scope, category)
        return None
    except Exception as exc:
        policy.failed(usage_scope, "invalid_response", request_id)
        log.warning("Gemini [%s] invalid response: %s", usage_scope, type(exc).__name__)
        return None


def grounded_text(text: str, metadata: dict) -> Optional[str]:
    """Only publish research with API-provided, claim-linked web sources."""
    chunks = metadata.get("groundingChunks") or []
    sources = {}
    citations = {}
    for support in metadata.get("groundingSupports") or []:
        segment = (support.get("segment") or {}).get("text", "")
        if not segment or segment not in text:
            continue
        indices = []
        for index in support.get("groundingChunkIndices") or []:
            if not isinstance(index, int) or not 0 <= index < len(chunks):
                continue
            web = chunks[index].get("web") or {}
            uri = web.get("uri", "")
            if not uri.startswith("https://"):
                continue
            sources[index] = (web.get("title") or uri, uri)
            indices.append(index)
        if indices:
            citations.setdefault(segment, set()).update(indices)
    if not text or not sources:
        return None
    # Replace source segments once, escaping model content for Telegram.
    rendered = escape(text, quote=False)
    for segment, indices in citations.items():
        safe = escape(segment, quote=False)
        rendered = rendered.replace(safe, safe + " " + "".join(f"[{i + 1}]" for i in sorted(indices)), 1)
    references = "\n".join(
        f'[{i + 1}] {escape(title, quote=False)} — {escape(uri, quote=False)}'
        for i, (title, uri) in sorted(sources.items())
    )
    return rendered + "\n\n查證來源\n" + references


async def test_gemini_connection(session: aiohttp.ClientSession) -> bool:
    if not GEMINI_API_KEY:
        log.warning("GEMINI_API_KEY is not set")
        return False
    text = await call_gemini(session, "Ping", timeout=10)
    if text is not None:
        log.info("Gemini API key verified successfully! Connection is working.")
        return True
    log.warning("Gemini probe unavailable or deferred; see usage state for error/cooldown/budget")
    return False
