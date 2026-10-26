import asyncio
from unittest.mock import AsyncMock

import pytest

import yt_search_probe as probe


@pytest.mark.parametrize("response", ["supported claim [1]", None])
def test_probe_uses_owned_ledger_and_keeps_grounding_enabled(monkeypatch, response):
    call = AsyncMock(return_value=response)
    monkeypatch.setattr(probe, "call_gemini", call)
    if response:
        asyncio.run(probe.main())
    else:
        with pytest.raises(RuntimeError, match="validated citations"):
            asyncio.run(probe.main())
    assert call.await_args.kwargs["usage_scope"] == "youtube"
    assert call.await_args.kwargs["google_search"] is True


def test_fixed_probe_error_redacts_sensitive_tokens(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "private-key")
    message = "private-key projects/private-project-name/path https://example.org/?key=private-key 1234567890123456789012345 not found"
    result = probe.safe_probe_error(message)
    assert "private-key" not in result
    assert "private-project-name" not in result
    assert "https://" not in result
    assert "1234567890123456789012345" not in result
    assert "not found" in result
