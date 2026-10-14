import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

import delivered_flashes as df
import event_briefing as eb
import jin10_monitor as jm
import flash_service as service


@pytest.fixture
def now(monkeypatch):
    value = datetime(2026, 9, 16, 19, 30, tzinfo=eb.TAIPEI)
    monkeypatch.setattr(eb.time, "time", lambda: value.timestamp())
    return value


def valid_response(ids=None):
    return json.dumps({"sections": [
        {"title": f"段落 {i}", "body": "分析<&>" * 60, "source_ids": ids or [1]}
        for i in range(4)]})


def test_journal_retention_and_corruption(now):
    df.save_json(df.STATE_FILE, {"since": now.timestamp() - 100,
        "items": [{"sent_at": now.timestamp() - 73 * 3600, "summary": "old"}]})
    df.record_delivery("delivered", source="test", url="")
    assert [item["summary"] for item in df.load_deliveries()["items"]] == ["delivered"]
    df.STATE_FILE.write_text("invalid")
    with pytest.raises(ValueError):
        df.record_delivery("new", source="test", url="")


def test_seed_journal_starts_coverage_at_initialization(now):
    df.STATE_FILE.write_text("{}")
    df.initialize()
    assert df.load_deliveries() == {"since": now.timestamp(), "items": []}


def test_service_supervises_briefing_and_cancels_peers(monkeypatch):
    cancelled = []
    async def wait_forever():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)
    async def stop():
        return
    monkeypatch.setattr(service.jin10_monitor, "main", wait_forever)
    monkeypatch.setattr(service.telegram_assistant, "main", wait_forever)
    monkeypatch.setattr(service.event_briefing, "main", stop)
    with pytest.raises(RuntimeError, match="stopped unexpectedly"):
        asyncio.run(service.main())
    assert len(cancelled) == 2
    assert df.STATE_FILE.exists()


@pytest.mark.parametrize("sent", [True, False])
def test_monitor_records_only_confirmed_deliveries(monkeypatch, sent):
    monkeypatch.setattr(jm, "remember_news", lambda *args, **kwargs: None)
    monkeypatch.setattr(jm, "GEMINI_API_KEY", "test")
    monkeypatch.setattr(jm, "GEMINI_AVAILABLE", True)
    monkeypatch.setattr(jm, "KEYWORDS", ["BTC"])
    monkeypatch.setattr(jm, "MAX_TIER_TO_SEND", 2)
    monkeypatch.setattr(jm, "summarize_with_gemini", AsyncMock(return_value={
        "tier": "HIGH", "relevant": True, "message": "delivered summary"}))
    monkeypatch.setattr(jm, "send_telegram_message", AsyncMock(return_value=sent))
    asyncio.run(jm.handle_item(None, {"id": "1", "data": {"content": "BTC"}}))
    assert len(df.load_deliveries()["items"]) == int(sent)


def test_build_includes_all_today_deliveries_and_escapes_output(now, monkeypatch):
    midnight = now.replace(hour=0, minute=0).timestamp()
    df.save_json(df.STATE_FILE, {"since": midnight, "items": [
        {"sent_at": midnight - 1, "summary": "yesterday"},
        {"sent_at": midnight, "summary": "first"},
        {"sent_at": now.timestamp(), "summary": "last"},
        {"sent_at": now.timestamp() + 1, "summary": "future"}]})
    model = AsyncMock(return_value=valid_response([1, 2]))
    monkeypatch.setattr(eb, "call_gemini", model)
    messages = asyncio.run(eb.build_messages(None, now + timedelta(hours=1), ["CPI"], now))
    prompt = json.loads(model.call_args.args[1])
    assert [source["summary"] for source in prompt["sources"]] == ["first", "last"]
    assert model.call_args.kwargs["usage_scope"] == "live"
    assert len(messages) == 4
    assert "&lt;&amp;&gt;" in messages[0]
    assert all(len(message.encode("utf-16-le")) // 2 < 4096 for message in messages)


@pytest.mark.parametrize("raw", [None, "bad", "{}", json.dumps({"sections": [
    {"title": "test", "body": "short", "source_ids": [1]}] * 4}),
    valid_response().replace('"source_ids": [1]', '"source_ids": [999]')])
def test_invalid_model_output_rejected(now, monkeypatch, raw):
    df.record_delivery("news", source="test", url="")
    monkeypatch.setattr(eb, "call_gemini", AsyncMock(return_value=raw))
    with pytest.raises(ValueError):
        asyncio.run(eb.build_messages(None, now + timedelta(hours=1), ["CPI"], now))


def test_empty_journal_does_not_call_ai(now, monkeypatch):
    model = AsyncMock()
    monkeypatch.setattr(eb, "call_gemini", model)
    result = asyncio.run(eb.build_messages(None, now + timedelta(hours=1), ["CPI"], now))
    assert "無法產生事件前分析" in result[0]
    model.assert_not_awaited()


def test_short_draft_is_repaired_with_exact_feedback(now, monkeypatch):
    df.record_delivery("news", source="test", url="")
    short = json.dumps({"sections": [
        {"title": "section", "body": "short", "source_ids": [1]}] * 4})
    model = AsyncMock(side_effect=[short, valid_response()])
    monkeypatch.setattr(eb, "call_gemini", model)
    messages = asyncio.run(eb.build_messages(None, now + timedelta(hours=1), ["CPI"], now))
    assert len(messages) == 4
    assert model.await_count == 2
    correction = json.loads(model.call_args.args[1])
    assert "body_chars=20" in correction["validation_error"]
    assert correction["original_input"]["sources"][0]["summary"] == "news"


def test_unavailable_model_does_not_trigger_immediate_extra_request(now, monkeypatch):
    df.record_delivery("news", source="test", url="")
    model = AsyncMock(return_value=None)
    monkeypatch.setattr(eb, "call_gemini", model)
    with pytest.raises(ValueError, match="unavailable"):
        asyncio.run(eb.build_messages(None, now + timedelta(hours=1), ["CPI"], now))
    model.assert_awaited_once()


def test_invalid_repair_is_bounded_and_never_delivered(now, monkeypatch):
    df.record_delivery("news", source="test", url="")
    model = AsyncMock(return_value="{}")
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(eb, "call_gemini", model)
    monkeypatch.setattr(eb, "send_telegram_message", sender)
    when = now + timedelta(hours=1)
    asyncio.run(eb.tick(None, [(when, "CPI")], now=now))
    assert model.await_count == 2
    sender.assert_awaited_once()
    assert "尚未產生有效分析" in sender.call_args.args[2]
    progress = eb.load_state()[when.isoformat()]
    assert progress["next"] == 0 and "messages" not in progress
    assert progress["last_error"] == "AI briefing unavailable or invalid"


def test_missing_source_coverage_rejected(now, monkeypatch):
    df.record_delivery("first", source="test", url="")
    df.record_delivery("second", source="test", url="")
    monkeypatch.setattr(eb, "call_gemini", AsyncMock(return_value=valid_response()))
    with pytest.raises(ValueError, match="omitted"):
        asyncio.run(eb.build_messages(None, now + timedelta(hours=1), ["CPI"], now))


def test_oversized_input_is_not_silently_truncated(now, monkeypatch):
    df.record_delivery("news" * 80000, source="test", url="")
    model = AsyncMock()
    monkeypatch.setattr(eb, "call_gemini", model)
    with pytest.raises(ValueError, match="input limit"):
        asyncio.run(eb.build_messages(None, now + timedelta(hours=1), ["CPI"], now))
    model.assert_not_awaited()


def test_progress_save_failure_prevents_send(now, monkeypatch):
    monkeypatch.setattr(eb, "build_messages", AsyncMock(return_value=["analysis"]))
    def fail_save(*args):
        raise OSError("disk unavailable")
    monkeypatch.setattr(eb, "save_json", fail_save)
    sender = AsyncMock()
    monkeypatch.setattr(eb, "send_telegram_message", sender)
    with pytest.raises(OSError):
        asyncio.run(eb.tick(None, [(now + timedelta(hours=1), "CPI")], now=now))
    sender.assert_not_awaited()


def test_window_grouping_and_restart_resumes_only_unsent_segments(now, monkeypatch):
    when = now + timedelta(hours=1)
    events = [(when, "CPI"), (when, "非農就業"),
              (now, "already released"), (when + timedelta(seconds=1), "too early")]
    build = AsyncMock(return_value=["part 1", "part 2", "part 3"])
    sender = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(eb, "build_messages", build)
    monkeypatch.setattr(eb, "send_telegram_message", sender)
    asyncio.run(eb.tick(None, events, now=now))
    build.assert_awaited_once()
    assert build.call_args.args[2] == ["CPI", "非農就業"]
    assert eb.load_state()[when.isoformat()]["next"] == 1
    sender.side_effect = None
    sender.return_value = True
    sender.reset_mock()
    asyncio.run(eb.tick(None, events, now=now))
    assert [call.args[2] for call in sender.call_args_list] == ["part 2", "part 3"]
    build.assert_awaited_once()
    sender.reset_mock()
    asyncio.run(eb.tick(None, events, now=now))
    sender.assert_not_awaited()


def test_failure_notice_once_and_retry_backoff(now, monkeypatch):
    events = [(now + timedelta(hours=1), "CPI")]
    build = AsyncMock(side_effect=ValueError("invalid AI"))
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(eb, "build_messages", build)
    monkeypatch.setattr(eb, "send_telegram_message", sender)
    asyncio.run(eb.tick(None, events, now=now))
    asyncio.run(eb.tick(None, events, now=now + timedelta(minutes=1)))
    build.assert_awaited_once()
    asyncio.run(eb.tick(None, events, now=now + timedelta(minutes=5)))
    assert build.await_count == 2
    sender.assert_awaited_once()
    assert "尚未產生有效分析" in sender.call_args.args[2]


def test_slow_model_never_sends_after_release(now, monkeypatch):
    when = now + timedelta(minutes=1)
    monkeypatch.setattr(eb.time, "time", lambda: when.timestamp())
    monkeypatch.setattr(eb, "build_messages", AsyncMock(return_value=["too late"]))
    sender = AsyncMock()
    monkeypatch.setattr(eb, "send_telegram_message", sender)
    asyncio.run(eb.tick(None, [(when, "CPI")], now=now))
    sender.assert_not_awaited()


def test_corrupt_progress_stops_before_send(now, monkeypatch):
    eb.STATE_FILE.write_text('{"bad": {"at": 1, "next": -1}}')
    sender = AsyncMock()
    monkeypatch.setattr(eb, "send_telegram_message", sender)
    with pytest.raises(ValueError):
        asyncio.run(eb.tick(None, [(now + timedelta(hours=1), "CPI")], now=now))
    sender.assert_not_awaited()


def test_preview_waits_for_new_delivery_then_resumes_after_restart(now, monkeypatch):
    events = [(now + timedelta(hours=3), "CPI")]
    build = AsyncMock(return_value=["first", "second"])
    sender = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(eb, "build_messages", build)
    monkeypatch.setattr(eb, "send_telegram_message", sender)
    df.save_json(df.STATE_FILE, {"since": now.timestamp() - 10, "items": [
        {"sent_at": now.timestamp() - 1, "summary": "before request"}]})
    asyncio.run(eb.tick(None, events, now=now, preview_id="test"))
    build.assert_not_awaited()
    sender.assert_not_awaited()
    df.record_delivery("new", source="test", url="")
    # A later run has no environment input; the saved request still triggers.
    asyncio.run(eb.tick(None, events, now=now + timedelta(seconds=1)))
    assert eb.load_state()["preview:test"]["next"] == 1
    assert "手動預覽" in sender.call_args_list[0].args[2]
    sender.side_effect = None
    sender.return_value = True
    sender.reset_mock()
    asyncio.run(eb.tick(None, events, now=now + timedelta(seconds=2)))
    sender.assert_awaited_once()
    assert sender.call_args.args[2].endswith("second")
    assert eb.load_state()["preview:test"]["done"]
    build.assert_awaited_once()
    sender.reset_mock()
    asyncio.run(eb.tick(None, events, now=now + timedelta(seconds=3), preview_id="test"))
    sender.assert_not_awaited()
    assert events[0][0].isoformat() not in eb.load_state()


def test_preview_requires_real_future_event_and_expires(now, monkeypatch):
    build = AsyncMock()
    monkeypatch.setattr(eb, "build_messages", build)
    asyncio.run(eb.tick(None, [], now=now, preview_id="test"))
    df.record_delivery("new", source="test", url="")
    asyncio.run(eb.tick(None, [(now, "past CPI")], now=now))
    build.assert_not_awaited()
    later = now + timedelta(days=3)
    asyncio.run(eb.tick(None, [(later + timedelta(hours=3), "CPI")], now=later))
    build.assert_not_awaited()
