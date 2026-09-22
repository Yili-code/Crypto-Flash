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


@pytest.fixture
def model(monkeypatch):
    mock = AsyncMock(return_value=json.dumps({
        "overview": "政策仍有變數", "points": [
            {"title": "Fed 發言", "detail": "官員稱若通膨不降仍可能升息。", "source_ids": [1]},
        ], "watch": "通膨是否降溫",
    }, ensure_ascii=False))
    monkeypatch.setattr(dd, "call_gemini", mock)
    return mock


def test_daily_digest_uses_taipei_calendar_and_importance(daily_items, model):
    day, _ = daily_items
    reply = asyncio.run(dd.build_digest(None, day))
    payload = json.loads(model.call_args.args[1])
    assert [s["summary"] for s in payload["sources"]] == ["Critical event", "First event"]
    assert "30 秒掌握大事" in reply and "Fed 發言" in reply
    assert "未分級 1" in reply and "不保證全天完整" in reply
    assert "HIGH" not in reply and "Critical event" not in reply


def test_empty_archive_explains_missing_coverage(monkeypatch, model):
    monkeypatch.setattr(dd, "load_archive", lambda: [])
    assert "並不代表" in asyncio.run(dd.build_digest(None, date(2026, 9, 8)))
    model.assert_not_awaited()


def test_digest_deduplicates_summaries(daily_items, model):
    day, items = daily_items
    start = items[0]["ts"]
    items[:] = [{"ts": start + i, "tier": "HIGH", "summary": "Same event"} for i in range(3)]
    asyncio.run(dd.build_digest(None, day))
    assert len(json.loads(model.call_args.args[1])["sources"]) == 1


def test_no_eligible_summaries_never_sends_raw(daily_items, model):
    day, items = daily_items
    items[:] = [items[2]]
    reply = asyncio.run(dd.build_digest(None, day))
    assert "沒有可整理" in reply and "RAW" not in reply
    model.assert_not_awaited()


def test_input_limit_discloses_omissions(daily_items, model, monkeypatch):
    day, _ = daily_items
    monkeypatch.setattr(dd, "MAX_INPUT_CHARS", 120)
    reply = asyncio.run(dd.build_digest(None, day))
    assert "未納入" in reply
    assert len(json.loads(model.call_args.args[1])["sources"]) == 1


@pytest.mark.parametrize("raw", [None, "broken", "[]", '{}',
    json.dumps({"overview": "x", "points": [], "watch": ""}),
    json.dumps({"overview": "x", "points": [{"title": "a", "detail": "b", "source_ids": [99]}], "watch": ""}),
    json.dumps({"overview": "x" * 61, "points": [{"title": "a", "detail": "b", "source_ids": [1]}], "watch": ""}),
    json.dumps({"overview": "x" * 60, "points": [
        {"title": str(i), "detail": "b" * 85, "source_ids": [1]} for i in range(3)], "watch": ""}),
])
def test_failed_or_invalid_model_output_is_not_a_digest(daily_items, model, raw):
    model.return_value = raw
    with pytest.raises(dd.DigestUnavailable):
        asyncio.run(dd.build_digest(None, daily_items[0]))


def test_render_escapes_html_and_preserves_complete_text():
    raw = json.dumps({"overview": "<Fed>&", "points": [
        {"title": "<標題>", "detail": "完整句子 & 😀", "source_ids": [1]}], "watch": ""})
    result = dd.render_summary(raw, {1})
    assert "&lt;Fed&gt;&amp;" in result and "完整句子 &amp; 😀" in result
    assert len(result.encode("utf-16-le")) // 2 < 4096


def test_model_failure_notifies_but_does_not_mark_delivered(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    monkeypatch.setattr(dd, "DIGEST_STATE_FILE", path)
    monkeypatch.setattr(dd, "build_digest", AsyncMock(side_effect=dd.DigestUnavailable))
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(dd, "send_telegram_message", sender)
    with pytest.raises(dd.DigestUnavailable):
        asyncio.run(dd.main())
    assert dd.FAILURE_NOTICE in sender.call_args.args[2]
    assert not path.exists()


def test_failed_send_does_not_mark_digest_delivered(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    monkeypatch.setattr(dd, "DIGEST_STATE_FILE", state)
    monkeypatch.setattr(dd, "build_digest", AsyncMock(return_value="Digest"))
    monkeypatch.setattr(dd, "send_telegram_message", AsyncMock(return_value=False))
    with pytest.raises(RuntimeError, match="delivery failed"):
        asyncio.run(dd.main())
    assert not state.exists()


def test_successful_digest_is_not_sent_twice(tmp_path, monkeypatch):
    monkeypatch.setattr(dd, "DIGEST_STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(dd, "build_digest", AsyncMock(return_value="Digest"))
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


def test_scheduled_digest_uses_separate_persisted_budget(tmp_path, monkeypatch):
    import gemini_policy as policy
    monkeypatch.setenv("GEMINI_DIGEST_DAILY_REQUESTS", "1")
    assert policy.reserve("digest", "config", "first") is None
    assert policy.reserve("digest", "config", "second") == "daily_budget"
    assert policy.reserve("live", "config", "live-first") is None
    assert policy.read_state("digest")["used"] == 1
    assert policy.state_path("digest") != policy.state_path("live")


def test_scheduled_delivery_routes_digest_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(dd, "DIGEST_STATE_FILE", tmp_path / "state.json")
    builder = AsyncMock(return_value="Digest")
    monkeypatch.setattr(dd, "build_digest", builder)
    monkeypatch.setattr(dd, "send_telegram_message", AsyncMock(return_value=True))
    asyncio.run(dd.main())
    assert builder.call_args.kwargs == {"usage_scope": "digest"}
