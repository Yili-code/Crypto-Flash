"""Minimal stand-ins for the aiohttp objects the senders talk to."""

import json


class FakeResponse:
    """One canned HTTP response, usable as `async with session.post(...) as resp`."""

    def __init__(self, status: int, body: str = "", json_data=None):
        self.status = status
        self._body = body
        self._json = json_data

    async def text(self) -> str:
        return self._body

    async def json(self):
        return self._json if self._json is not None else json.loads(self._body or "{}")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    """Hands out queued responses and records every request made."""

    def __init__(self, responses=()):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def _next(self, method: str, url: str, kwargs: dict) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        if self._responses:
            return self._responses.pop(0)
        return FakeResponse(200, '{"ok": true}')

    def post(self, url, **kwargs):
        return self._next("POST", url, kwargs)

    def get(self, url, **kwargs):
        return self._next("GET", url, kwargs)
