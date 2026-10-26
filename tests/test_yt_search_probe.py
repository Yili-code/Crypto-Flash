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
