import asyncio
import json

import pytest

import yt_monitor as yt

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015">
  <title>加密龐克</title>
  <entry>
    <yt:videoId>newest</yt:videoId>
    <title>New &amp; shiny</title>
    <link rel="alternate" href="https://youtu.be/newest"/>
    <published>2026-09-08T00:00:00+00:00</published>
  </entry>
  <entry>
    <yt:videoId>older</yt:videoId>
    <title>Older</title>
    <link rel="alternate" href="https://youtu.be/older"/>
    <published>2026-09-07T00:00:00+00:00</published>
  </entry>
  <entry>
    <title>No video id, must be skipped</title>
  </entry>
</feed>"""


def channel_cfg(**overrides):
    cfg = {"name": "c", "channel_id": "UC123", "system_prompt": "", "max_new_per_run": 3}
    cfg.update(overrides)
    return cfg


@pytest.fixture
def wired(tmp_path, monkeypatch):
    """process_channel with the network and Telegram replaced by recorders."""
    monkeypatch.setattr(yt, "SEEN_STATE_FILE", tmp_path / "seen.json")

    async def fake_fetch_feed(session, url):
        return FEED

    async def fake_summarize(session, url, system_prompt=""):
        return "summary"

    sent: list[str] = []
    outcome = {"ok": True}

    async def fake_send(session, chat_id, text, bot_token=None, **kwargs):
        sent.append(text)
        return outcome["ok"]

    monkeypatch.setattr(yt, "fetch_feed", fake_fetch_feed)
    monkeypatch.setattr(yt, "summarize_video", fake_summarize)
    monkeypatch.setattr(yt, "send_telegram_message", fake_send)
    return sent, outcome


# ─── feed parsing ──────────────────────────────────────────────────────────────

def test_parse_feed_returns_entries_oldest_first():
    channel_title, entries = yt.parse_feed(FEED)
    assert channel_title == "加密龐克"
    assert [e["video_id"] for e in entries] == ["older", "newest"]


def test_parse_feed_skips_entries_without_a_video_id():
    _, entries = yt.parse_feed(FEED)
    assert len(entries) == 2


def test_parse_feed_keeps_the_raw_title_and_link():
    _, entries = yt.parse_feed(FEED)
    assert entries[1]["title"] == "New & shiny"
    assert entries[1]["link"] == "https://youtu.be/newest"


# ─── message assembly ──────────────────────────────────────────────────────────

def test_format_message_escapes_the_title_but_keeps_the_summary_markup():
    msg = yt.format_message("Chan & Co", "BTC <5% & ETH", "https://x/1", "<b>summary</b>")
    assert "BTC &lt;5% &amp; ETH" in msg
    assert "Chan &amp; Co" in msg
    assert "<b>summary</b>" in msg


def test_format_message_escapes_the_title_in_the_fallback_too():
    msg = yt.format_message("c", "A & B", "https://x/1", None)
    assert "A &amp; B" in msg
    assert "https://x/1" in msg


# ─── channel configuration ─────────────────────────────────────────────────────

def test_load_channel_configs_skips_invalid_and_duplicate_entries(tmp_path, monkeypatch):
    path = tmp_path / "channels.json"
    path.write_text(json.dumps([
        {"name": "a", "channel_id": "1"},
        {"name": "a", "channel_id": "2"},   # duplicate name: the two would clobber each other's state
        {"name": "", "channel_id": "3"},    # no name
        {"name": "b"},                      # no channel_id
        "not-an-object",
    ]), encoding="utf-8")
    monkeypatch.setattr(yt, "CHANNELS_CONFIG_FILE", path)
    assert [c["name"] for c in yt.load_channel_configs()] == ["a"]


def test_load_channel_configs_clamps_a_zero_limit(tmp_path, monkeypatch):
    # max_new_per_run == 0 would make new_entries[-0:] select the entire backlog.
    path = tmp_path / "channels.json"
    path.write_text(json.dumps([{"name": "c", "channel_id": "1", "max_new_per_run": "0"}]), encoding="utf-8")
    monkeypatch.setattr(yt, "CHANNELS_CONFIG_FILE", path)
    assert yt.load_channel_configs()[0]["max_new_per_run"] == 1


def test_load_channel_configs_tolerates_a_missing_or_broken_file(tmp_path, monkeypatch):
    monkeypatch.setattr(yt, "CHANNELS_CONFIG_FILE", tmp_path / "missing.json")
    assert yt.load_channel_configs() == []

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(yt, "CHANNELS_CONFIG_FILE", broken)
    assert yt.load_channel_configs() == []

    wrong_shape = tmp_path / "wrong.json"
    wrong_shape.write_text('{"a": 1}', encoding="utf-8")
    monkeypatch.setattr(yt, "CHANNELS_CONFIG_FILE", wrong_shape)
    assert yt.load_channel_configs() == []


# ─── seen-id state ─────────────────────────────────────────────────────────────

def test_seen_state_round_trips_and_trims(tmp_path, monkeypatch):
    monkeypatch.setattr(yt, "SEEN_STATE_FILE", tmp_path / "seen.json")
    monkeypatch.setattr(yt, "MAX_SEEN_IDS_PER_CHANNEL", 3)
    yt.save_seen_state({"a": ["1", "2", "3", "4", "5"]})
    assert yt.load_seen_state() == {"a": ["3", "4", "5"]}


def test_load_seen_state_rejects_corrupt_content(tmp_path, monkeypatch):
    path = tmp_path / "seen.json"
    monkeypatch.setattr(yt, "SEEN_STATE_FILE", path)
    assert yt.load_seen_state() == {}

    path.write_text("[]", encoding="utf-8")
    with pytest.raises(yt.SeenStateError):
        yt.load_seen_state()

    path.write_text('{"a": ["ok", 5], "b": "not-a-list"}', encoding="utf-8")
    with pytest.raises(yt.SeenStateError):
        yt.load_seen_state()

    path.write_text('{broken', encoding="utf-8")
    with pytest.raises(yt.SeenStateError):
        yt.load_seen_state()


def test_save_failure_is_not_silently_ignored(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(yt, "SEEN_STATE_FILE", blocker / "seen.json")
    with pytest.raises(yt.SeenStateError):
        yt.save_seen_state({"c": ["older"]})


# ─── per-channel flow ──────────────────────────────────────────────────────────

def test_first_run_only_warms_dedup_and_pushes_nothing(wired):
    sent, _ = wired
    state = {}
    asyncio.run(yt.process_channel(None, channel_cfg(), state))
    assert sent == []
    assert state["c"] == ["older", "newest"]


def test_a_new_video_is_pushed_and_marked_read(wired):
    sent, _ = wired
    state = {"c": ["older"]}
    asyncio.run(yt.process_channel(None, channel_cfg(), state))
    assert len(sent) == 1
    assert state["c"] == ["older", "newest"]


def test_restart_does_not_resend_delivered_video(wired):
    sent, _ = wired
    asyncio.run(yt.process_channel(None, channel_cfg(), {"c": ["older"]}))
    asyncio.run(yt.process_channel(None, channel_cfg(), yt.load_seen_state()))
    assert len(sent) == 1


def test_duplicate_feed_entries_are_only_sent_once(wired, monkeypatch):
    sent, _ = wired
    _, entries = yt.parse_feed(FEED)
    monkeypatch.setattr(yt, "parse_feed", lambda xml: ("c", entries + entries))
    asyncio.run(yt.process_channel(None, channel_cfg(), {"c": ["older"]}))
    assert len(sent) == 1


def test_main_stops_before_network_when_state_cannot_be_saved(wired, monkeypatch):
    sent, _ = wired
    monkeypatch.setattr(yt, "load_channel_configs", lambda: [channel_cfg()])

    def fail_save(state):
        raise yt.SeenStateError("disk unavailable")

    monkeypatch.setattr(yt, "save_seen_state", fail_save)
    with pytest.raises(yt.SeenStateError):
        asyncio.run(yt.main())
    assert sent == []


def test_main_does_not_continue_after_receipt_save_failure(wired, monkeypatch):
    monkeypatch.setattr(yt, "load_channel_configs", lambda: [channel_cfg(), channel_cfg(name="other")])
    processed = []

    async def accessible(*args):
        return True

    async def fail_process(session, cfg, state):
        processed.append(cfg["name"])
        raise yt.SeenStateError("disk unavailable")

    monkeypatch.setattr(yt, "check_chat_access", accessible)
    monkeypatch.setattr(yt, "process_channel", fail_process)
    with pytest.raises(yt.SeenStateError):
        asyncio.run(yt.main())
    assert processed == ["c"]


def test_a_failed_push_leaves_the_video_unread_for_the_next_run(wired):
    sent, outcome = wired
    outcome["ok"] = False  # e.g. "Bad Request: chat not found"
    state = {"c": ["older"]}
    asyncio.run(yt.process_channel(None, channel_cfg(), state))
    assert len(sent) == 1
    assert state["c"] == ["older"]


def test_a_backlog_over_the_limit_is_trimmed_and_the_rest_marked_read(wired):
    sent, _ = wired
    state = {"c": ["seed"]}
    asyncio.run(yt.process_channel(None, channel_cfg(max_new_per_run=1), state))
    assert len(sent) == 1                       # only the newest is pushed
    assert "older" in state["c"]                # the skipped one is marked read, not re-pushed
    assert state["c"][-1] == "newest"


def test_nothing_happens_when_there_are_no_new_videos(wired):
    sent, _ = wired
    state = {"c": ["older", "newest"]}
    asyncio.run(yt.process_channel(None, channel_cfg(), state))
    assert sent == []


def test_a_failed_feed_fetch_is_a_no_op(monkeypatch, tmp_path):
    monkeypatch.setattr(yt, "SEEN_STATE_FILE", tmp_path / "seen.json")

    async def no_feed(session, url):
        return None

    monkeypatch.setattr(yt, "fetch_feed", no_feed)
    state = {"c": ["older"]}
    asyncio.run(yt.process_channel(None, channel_cfg(), state))
    assert state == {"c": ["older"]}
