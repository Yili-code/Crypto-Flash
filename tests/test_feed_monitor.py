import asyncio
import json

import feed_monitor as fm


RSS = b"""<?xml version="1.0"?>
<rss><channel>
  <item><guid>one</guid><title>BTC &amp; ETF</title><description><![CDATA[<b>Market</b> update]]></description><link>https://example.com/one</link></item>
  <item><guid>two</guid><title>Ethereum update</title><description>Details</description><link>https://example.com/two</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><id>a1</id><title>SEC crypto rule</title><summary>New proposal</summary><link href="https://example.com/a1" /></entry>
</feed>"""


def test_parse_feed_supports_rss_and_strips_markup():
    items = fm.parse_feed(RSS, "Example")
    assert items[0]["data"] == {"title": "BTC & ETF", "content": "Market update"}
    assert items[0]["source"] == "Example"
    assert items[0]["url"] == "https://example.com/one"
    assert items[0]["id"].startswith("feed:")


def test_parse_feed_supports_atom_links():
    item = fm.parse_feed(ATOM, "Official")[0]
    assert item["data"]["title"] == "SEC crypto rule"
    assert item["url"] == "https://example.com/a1"


def test_load_feeds_accepts_only_unique_https_sources(tmp_path):
    path = tmp_path / "feeds.json"
    path.write_text(json.dumps([
        {"name": "Good", "url": "https://example.com/feed"},
        {"name": "Good", "url": "https://duplicate.example/feed"},
        {"name": "Unsafe", "url": "http://example.com/feed"},
        {"name": "Off", "url": "https://example.com/off", "enabled": False},
    ]), encoding="utf-8")
    assert fm.load_feeds(path) == [{"name": "Good", "url": "https://example.com/feed"}]


def test_poll_once_warms_then_emits_only_new_entries(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(fm, "FEED_STATE_FILE", state_file)
    batches = [[{"id": "1"}], [{"id": "2"}, {"id": "1"}]]

    async def fake_fetch(session, feed):
        return batches.pop(0)

    emitted = []

    async def emit(item):
        emitted.append(item["id"])

    monkeypatch.setattr(fm, "fetch_feed", fake_fetch)

    async def scenario():
        state = {}
        feeds = [{"name": "Example", "url": "https://example.com/feed"}]
        await fm.poll_once(None, feeds, state, emit)
        await fm.poll_once(None, feeds, state, emit)
        return state

    state = asyncio.run(scenario())
    assert emitted == ["2"]
    assert state["Example"] == ["2", "1"]
    assert json.loads(state_file.read_text(encoding="utf-8"))["Example"] == ["2", "1"]
