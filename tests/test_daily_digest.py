import asyncio
import json
import time
from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest

import daily_digest as dd
import news_archive as archive
import jin10_monitor as jm


def test_archive_retains_three_days_deduplicates_and_prunes(tmp_path, monkeypatch):
    path = tmp_path / "archive.json"
    monkeypatch.setattr(archive, "ARCHIVE_FILE", path)
    now = time.time()
    path.write_text(json.dumps([
        {"id": "expired", "ts": now - 73 * 3600},
        {"id": "yesterday", "ts": now - 25 * 3600},
        {"id": "same", "ts": now - 10, "summary": "old"},
        {"ts": "invalid"}, None,
    ]), encoding="utf-8")
    archive.archive_news({"id": "same", "ts": now, "summary": "new"})
    items = archive.load_archive()
    assert [item["id"] for item in items] == ["yesterday", "same"]
    assert items[-1]["summary"] == "new"
    assert not path.with_suffix(".json.tmp").exists()


def test_monitor_archives_summary_even_below_push_threshold(monkeypatch):
    records = []
    monkeypatch.setattr(jm, "archive_news", records.append)
    monkeypatch.setattr(jm, "save_recent_news", lambda items: None)
    monkeypatch.setattr(jm, "recent_news", jm.deque(maxlen=80))
    monkeypatch.setattr(jm, "GEMINI_API_KEY", "test")
    monkeypatch.setattr(jm, "GEMINI_AVAILABLE", True)
    monkeypatch.setattr(jm, "KEYWORDS", ["BTC"])
    monkeypatch.setattr(jm, "MAX_TIER_TO_SEND", 1)
    monkeypatch.setattr(jm, "summarize_with_gemini", AsyncMock(return_value={
        "tier": "MEDIUM", "relevant": True, "message": "Saved summary",
    }))
    sender = AsyncMock()
    monkeypatch.setattr(jm, "send_telegram_message", sender)
    asyncio.run(jm.handle_item(None, {"id": "news-1", "data": {"content": "BTC news"}}))
    assert records[0]["summary"] == "Saved summary"
    assert records[0]["id"] == "news-1"
    sender.assert_not_awaited()


@pytest.fixture
def daily_items(monkeypatch):
    day = date(2026, 9, 8)
    start = datetime(2026, 9, 8, tzinfo=dd.DISPLAY_TZ).timestamp()
    items = [
        {"ts": start, "tier": "HIGH", "summary": "<b>First event</b>", "relevant": True},
        {"ts": start + 100, "tier": "CRITICAL", "summary": "Critical event", "relevant": True},
        {"ts": start + 200, "tier": None, "content": "RAW MUST NOT BE SENT"},
        {"ts": start + 300, "tier": "LOW", "summary": "Low event"},
        {"ts": start + 400, "tier": "HIGH", "summary": "Irrelevant", "relevant": False},
        {"ts": start - 1, "tier": "HIGH", "summary": "Previous day"},
        {"ts": start + 86400, "tier": "HIGH", "summary": "Next day"},
    ]
    monkeypatch.setattr(dd, "load_archive", lambda: items)
    return day, items


def test_daily_digest_uses_taipei_calendar_and_importance(daily_items):
    day, _ = daily_items
    reply = dd.build_digest(day)
    assert "紀錄 5 則" in reply and "HIGH/CRITICAL 2 則" in reply
    assert reply.index("Critical event") < reply.index("First event")
    for excluded in ("RAW MUST NOT BE SENT", "Low event", "Irrelevant", "Previous day", "Next day"):
        assert excluded not in reply
    assert "未分級 1" in reply and "不保證全天完整" in reply


def test_empty_archive_explains_missing_coverage(monkeypatch):
    monkeypatch.setattr(dd, "load_archive", lambda: [])
    assert "並不代表" in dd.build_digest(date(2026, 9, 8))


def test_digest_deduplicates_summaries_and_bounds_message(daily_items):
    day, items = daily_items
    start = items[0]["ts"]
    items[:] = [{"ts": start + i, "tier": "HIGH", "summary": f"{i} " + "&😀" * 300}
                for i in range(30)]
    reply = dd.build_digest(day)
    assert "&amp;" in reply
    assert len(reply.encode("utf-16-le")) // 2 < 4096
    items[:] = [{"ts": start + i, "tier": "HIGH", "summary": "Same event"} for i in range(3)]
    assert dd.build_digest(day).count("Same event") == 1


def test_failed_send_does_not_mark_digest_delivered(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    monkeypatch.setattr(dd, "DIGEST_STATE_FILE", state)
    monkeypatch.setattr(dd, "build_digest", lambda day: "Digest")
    monkeypatch.setattr(dd, "send_telegram_message", AsyncMock(return_value=False))
    with pytest.raises(RuntimeError, match="delivery failed"):
        asyncio.run(dd.main())
    assert not state.exists()


def test_successful_digest_is_not_sent_twice(tmp_path, monkeypatch):
    monkeypatch.setattr(dd, "DIGEST_STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(dd, "build_digest", lambda day: "Digest")
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(dd, "send_telegram_message", sender)
    asyncio.run(dd.main())
    asyncio.run(dd.main())
    sender.assert_awaited_once()


def test_corrupt_delivery_state_fails_before_sending(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    state.write_text("broken", encoding="utf-8")
    monkeypatch.setattr(dd, "DIGEST_STATE_FILE", state)
    sender = AsyncMock()
    monkeypatch.setattr(dd, "send_telegram_message", sender)
    with pytest.raises(RuntimeError, match="duplicate"):
        asyncio.run(dd.main())
    sender.assert_not_awaited()
