import asyncio
import json
from unittest.mock import AsyncMock

import pytest

import event_tracking as et
import telegram_assistant as qa
from fakes import FakeResponse


@pytest.fixture
def tracking(tmp_path, monkeypatch):
    monkeypatch.setattr(et, "EVENT_STATE_FILE", tmp_path / "tracking.json")
    monkeypatch.setattr(et.time, "time", lambda: 1000.0)
    items = []
    monkeypatch.setattr(et, "load_archive", lambda: items)
    return items


def news(identifier, ts, title="BTC news", summary=""):
    return {"id": identifier, "ts": ts, "title": title, "content": "", "summary": summary, "tier": "HIGH"}


def test_track_is_persistent_case_insensitive_and_idempotent(tracking):
    assert "已開始" in et.event_command_reply("track", "spot   ETF").text
    assert "已在追蹤" in et.event_command_reply("track", "SPOT ETF").text
    topics = et.load_topics()
    assert len(topics) == 1 and topics[0]["keyword"] == "spot ETF"
    assert topics[0]["cursor"] == [1000.0, ""]
    assert not et.EVENT_STATE_FILE.with_suffix(".json.tmp").exists()
    assert "已停止" in et.event_command_reply("untrack", "Spot ETF").text
    assert et.load_topics() == []


def test_updates_start_at_subscription_and_ack_only_after_delivery(tracking):
    et.event_command_reply("track", "BTC")
    tracking.extend([news("old", 999, "BTC previous"), news("new", 1001, "BTC fresh")])
    reply = et.event_command_reply("updates", "")
    assert "BTC fresh" in reply.text and "BTC previous" not in reply.text
    assert et.event_command_reply("updates", "").text == reply.text
    et.acknowledge_updates(reply)
    assert "沒有尚未" in et.event_command_reply("updates", "").text
    tracking.append(news("next", 1002, "BTC follow-up"))
    assert "BTC follow-up" in et.event_command_reply("updates", "").text


def test_same_timestamp_backlog_can_be_read_without_gaps(tracking):
    et.event_command_reply("track", "BTC")
    tracking.extend(news(str(i), 1001, f"BTC event {i}") for i in range(20))
    displayed = []
    for _ in range(3):
        reply = et.event_command_reply("updates", "")
        displayed.extend(line for line in reply.text.splitlines() if line.startswith("BTC event"))
        et.acknowledge_updates(reply)
    assert len(displayed) == len(set(displayed)) == 20
    assert "沒有尚未" in et.event_command_reply("updates", "").text


def test_overlapping_topics_show_one_event_and_advance_both(tracking):
    et.event_command_reply("track", "BTC")
    et.event_command_reply("track", "ETF")
    tracking.append(news("shared", 1001, "BTC ETF approved"))
    reply = et.event_command_reply("updates", "")
    assert reply.text.count("BTC ETF approved") == 1
    assert set(reply.progress) == {"btc", "etf"}
    et.acknowledge_updates(reply)
    assert "沒有尚未" in et.event_command_reply("updates", "ETF").text


def test_selected_topic_does_not_consume_other_topics(tracking):
    et.event_command_reply("track", "BTC")
    et.event_command_reply("track", "ETH")
    tracking.extend([news("btc", 1001), news("eth", 1002, "ETH news")])
    reply = et.event_command_reply("updates", "btc")
    assert "ETH news" not in reply.text
    et.acknowledge_updates(reply)
    assert "ETH news" in et.event_command_reply("updates", "").text


def test_timeline_shows_history_without_consuming_progress(tracking):
    et.event_command_reply("track", "BTC")
    tracking.extend([news("older", 999, "BTC old"), news("newer", 1001, "BTC new")])
    reply = et.event_command_reply("timeline", "btc")
    assert reply.text.index("BTC old") < reply.text.index("BTC new")
    assert "來源摘錄" in reply.text
    assert not reply.progress
    assert "BTC new" in et.event_command_reply("updates", "").text


def test_timeline_shows_latest_eight_in_chronological_order(tracking):
    tracking.extend(news(str(i), 1000 + i, f"BTC number {i:02d}") for i in range(15))
    reply = et.event_command_reply("timeline", "BTC").text
    assert "BTC number 06" not in reply
    assert reply.index("BTC number 07") < reply.index("BTC number 14")
    assert "8 / 15" in reply


def test_matching_includes_saved_summary_and_normalizes_phrases(tracking):
    et.event_command_reply("track", "spot ETF")
    tracking.append(news("one", 1001, "Other title", "<b>SPOT ETF</b> update"))
    reply = et.event_command_reply("updates", "")
    assert "SPOT ETF update" in reply.text and "摘要節錄" in reply.text
    assert "新增 1 則" in et.event_command_reply("tracks", "").text


def test_old_ack_cannot_skip_a_recreated_subscription(tracking, monkeypatch):
    et.event_command_reply("track", "BTC")
    tracking.append(news("one", 1001))
    reply = et.event_command_reply("updates", "")
    et.event_command_reply("untrack", "BTC")
    monkeypatch.setattr(et.time, "time", lambda: 1000.5)
    et.event_command_reply("track", "BTC")
    et.acknowledge_updates(reply)
    assert et.load_topics()[0]["cursor"] == [1000.5, ""]


@pytest.mark.parametrize("bad", ["broken", "[]", '{"version": 1, "topics": [null]}'])
def test_corrupt_state_is_not_overwritten(tracking, bad):
    et.EVENT_STATE_FILE.write_text(bad, encoding="utf-8")
    with pytest.raises(et.EventStateError):
        et.event_command_reply("track", "BTC")
    assert et.EVENT_STATE_FILE.read_text(encoding="utf-8") == bad


def test_write_failure_is_reported(tracking, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(et.Path, "write_text", fail)
    with pytest.raises(et.EventStateError, match="未能保存"):
        et.event_command_reply("track", "BTC")


def test_topic_limits_and_invalid_arguments(tracking):
    assert "用法" in et.event_command_reply("track", "").text
    assert "用法" in et.event_command_reply("tracks", "extra").text
    assert "字元" in et.event_command_reply("track", "a" * 41).text
    for i in range(et.MAX_TOPICS):
        et.event_command_reply("track", f"topic {i}")
    assert "最多追蹤" in et.event_command_reply("track", "one more").text
    assert len(et.load_topics()) == et.MAX_TOPICS


@pytest.mark.parametrize("pattern", ["&lt;&amp;" * 100, "😀" * 300])
def test_results_fit_telegram_and_do_not_lose_overflow(tracking, pattern):
    et.event_command_reply("track", "BTC")
    tracking.extend(news(str(i), 1001 + i, "BTC", pattern + str(i)) for i in range(12))
    total = 0
    for _ in range(12):
        reply = et.event_command_reply("updates", "")
        assert len(reply.text.encode("utf-16-le")) // 2 < 4096
        assert reply.text.count("<b>") == reply.text.count("</b>")
        if not reply.progress:
            break
        total += reply.text.count("摘要節錄")
        et.acknowledge_updates(reply)
    assert total == 12


@pytest.mark.parametrize("delivered", [True, False])
def test_listener_acknowledges_only_successful_sends(tracking, monkeypatch, delivered):
    et.event_command_reply("track", "BTC")
    tracking.append(news("one", 1001))
    monkeypatch.setattr(qa, "TELEGRAM_CHAT_ID", "allowed")
    monkeypatch.setattr(qa, "get_bot_username", AsyncMock(return_value="bot"))
    sender = AsyncMock(return_value=delivered)
    monkeypatch.setattr(qa, "send_telegram_message", sender)
    model = AsyncMock()
    monkeypatch.setattr(qa, "ask_gemini_qa", model)

    class Session:
        calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            if self.calls > 1:
                raise asyncio.CancelledError
            return FakeResponse(200, json_data={"result": [
                {"update_id": 1, "message": {"chat": {"id": "other", "type": "group"}, "text": "/untrack BTC"}},
                {"update_id": 2, "message": {"chat": {"id": "allowed", "type": "group"}, "text": "/updates@other"}},
                {"update_id": 3, "message": {"chat": {"id": "allowed", "type": "group"}, "text": "/updates@bot"}},
            ]})

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(qa.telegram_assistant_loop(Session()))
    sender.assert_awaited_once()
    model.assert_not_awaited()
    assert bool(et.event_command_reply("updates", "").progress) is not delivered


def test_event_commands_require_configured_chat(tracking, monkeypatch):
    monkeypatch.setattr(qa, "TELEGRAM_CHAT_ID", "")
    assert "TELEGRAM_CHAT_ID" in qa.prepare_event_reply("/track BTC", "bot").text
    assert not et.EVENT_STATE_FILE.exists()


def test_tracks_escape_keyword_and_do_not_mark_read(tracking):
    et.event_command_reply("track", "<ETF>")
    assert "&lt;ETF&gt;" in et.event_command_reply("tracks", "").text
    assert json.loads(et.EVENT_STATE_FILE.read_text())["topics"][0]["cursor"] == [1000.0, ""]
