import asyncio
import importlib
from unittest.mock import AsyncMock

import pytest

import gemini
import jin10_monitor as jm


@pytest.fixture
def monitor(monkeypatch):
    monkeypatch.setattr(jm, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(jm, "GEMINI_AVAILABLE", False)
    monkeypatch.setattr(jm, "KEYWORDS", ["BTC"])
    monkeypatch.setattr(jm, "remember_news", lambda *args: None)
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(jm, "send_telegram_message", sender)
    return sender


def test_startup_failure_recovers_and_only_pushes_summaries(monkeypatch, monitor):
    probe = AsyncMock(side_effect=[False, True])
    monkeypatch.setattr(jm, "test_gemini_connection", probe)
    monkeypatch.setattr(jm, "summarize_with_gemini", AsyncMock(return_value={
        "tier": "CRITICAL", "relevant": True, "message": "Recovered summary",
    }))
    pauses = []

    async def pause(delay):
        pauses.append(delay)
        await jm.handle_item(None, {"data": {"content": "BTC raw news"}})
        if len(pauses) == 1:
            monitor.assert_not_awaited()
        else:
            raise asyncio.CancelledError

    monkeypatch.setattr(jm.asyncio, "sleep", pause)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(jm.gemini_recovery_loop(None))
    assert probe.await_count == 2
    assert pauses == [jm.GEMINI_RECONNECT_DELAY] * 2
    monitor.assert_awaited_once()
    assert monitor.call_args.args[2] == "CRITICAL\nRecovered summary"


def test_runtime_failure_pauses_following_pushes(monkeypatch, monitor):
    monkeypatch.setattr(jm, "GEMINI_AVAILABLE", True)
    summary = AsyncMock(return_value=None)
    monkeypatch.setattr(jm, "summarize_with_gemini", summary)

    async def scenario():
        await jm.handle_item(None, {"data": {"content": "BTC first"}})
        await jm.handle_item(None, {"data": {"content": "BTC second"}})

    asyncio.run(scenario())
    assert not jm.GEMINI_AVAILABLE
    summary.assert_awaited_once()
    monitor.assert_not_awaited()


def test_missing_key_never_pushes_raw_news(monkeypatch, monitor):
    monkeypatch.setattr(jm, "GEMINI_API_KEY", "")
    probe = AsyncMock()
    monkeypatch.setattr(jm, "test_gemini_connection", probe)

    async def scenario():
        await jm.gemini_recovery_loop(None)
        await jm.handle_item(None, {"data": {"content": "BTC raw"}})

    asyncio.run(scenario())
    probe.assert_not_awaited()
    monitor.assert_not_awaited()


def test_recovery_probe_exception_is_retried(monkeypatch, monitor):
    probe = AsyncMock(side_effect=[OSError("connection reset"), True])
    monkeypatch.setattr(jm, "test_gemini_connection", probe)

    async def pause(delay):
        if jm.GEMINI_AVAILABLE:
            raise asyncio.CancelledError

    monkeypatch.setattr(jm.asyncio, "sleep", pause)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(jm.gemini_recovery_loop(None))
    assert probe.await_count == 2
    assert jm.GEMINI_AVAILABLE


def test_healthy_connection_does_not_send_extra_probes(monkeypatch, monitor):
    monkeypatch.setattr(jm, "GEMINI_AVAILABLE", True)
    probe = AsyncMock()
    monkeypatch.setattr(jm, "test_gemini_connection", probe)

    async def pause(delay):
        raise asyncio.CancelledError

    monkeypatch.setattr(jm.asyncio, "sleep", pause)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(jm.gemini_recovery_loop(None))
    probe.assert_not_awaited()


def test_non_object_summary_is_treated_as_failure(monkeypatch):
    monkeypatch.setattr(jm, "call_gemini", AsyncMock(return_value="[]"))
    assert asyncio.run(jm.summarize_with_gemini(None, "BTC")) is None


@pytest.mark.parametrize("model", ["", "   "])
def test_blank_model_uses_default(monkeypatch, model):
    with monkeypatch.context() as patch:
        patch.setenv("GEMINI_MODEL", model)
        importlib.reload(gemini)
        assert gemini.GEMINI_MODEL == "gemini-3.5-flash-lite"
        assert "/models/gemini-3.5-flash-lite:" in gemini.GEMINI_URL
    importlib.reload(gemini)
