import asyncio
from unittest.mock import AsyncMock

import classification_backlog as backlog
import jin10_monitor as monitor


def test_backlog_is_bounded_deduplicated_and_expires(tmp_path, monkeypatch):
    monkeypatch.setattr(backlog, "BACKLOG_FILE", tmp_path / "backlog.json")
    monkeypatch.setattr(backlog, "MAX_ITEMS", 2)
    monkeypatch.setattr(backlog, "MAX_AGE_SECONDS", 60)
    backlog.enqueue({"id": "one"}, now=100)
    backlog.enqueue({"id": "one", "value": "new"}, now=101)
    backlog.enqueue({"id": "two"}, now=102)
    backlog.enqueue({"id": "three"}, now=103)
    records = backlog.load(now=103)
    assert [record["id"] for record in records] == ["two", "three"]
    assert backlog.load(now=200) == []


def test_failed_flash_is_replayed_once_after_recovery(monkeypatch):
    item = {"id": "pending", "data": {"content": "BTC event"}}
    monkeypatch.setattr(monitor, "KEYWORDS", ["BTC"])
    monkeypatch.setattr(monitor, "GEMINI_API_KEY", "key")
    monkeypatch.setattr(monitor, "GEMINI_AVAILABLE", True)
    monkeypatch.setattr(monitor, "remember_news", lambda *args, **kwargs: None)
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(monitor, "send_telegram_message", sender)
    summary = AsyncMock(side_effect=[None, {
        "tier": "HIGH", "relevant": True, "message": "Recovered",
    }])
    monkeypatch.setattr(monitor, "summarize_with_gemini", summary)

    asyncio.run(monitor.handle_item(None, item))
    assert len(backlog.pending()) == 1
    monkeypatch.setattr(monitor, "GEMINI_AVAILABLE", True)
    asyncio.run(monitor.retry_classification_backlog(None))

    assert backlog.pending() == []
    sender.assert_awaited_once()
    assert summary.await_count == 2
