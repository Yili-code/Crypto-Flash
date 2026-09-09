import time

import common


def test_resolve_max_tier_accepts_level_names():
    assert common.resolve_max_tier("critical") == 1
    assert common.resolve_max_tier(" HIGH ") == 2
    assert common.resolve_max_tier("LOW") == 4


def test_resolve_max_tier_accepts_numbers():
    assert common.resolve_max_tier("2") == 2


def test_resolve_max_tier_falls_back_to_medium_on_garbage():
    assert common.resolve_max_tier("nonsense") == common.TIER_RANK["MEDIUM"]


def test_recent_news_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "NEWS_CONTEXT_FILE", tmp_path / "recent.json")
    now = time.time()
    common.save_recent_news([{"ts": now, "title": "a"}])
    assert common.load_recent_news() == [{"ts": now, "title": "a"}]


def test_load_recent_news_drops_stale_and_malformed_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "NEWS_CONTEXT_FILE", tmp_path / "recent.json")
    now = time.time()
    common.save_recent_news([
        {"ts": now, "title": "fresh"},
        {"ts": now - common.CONTEXT_MAX_AGE_SEC - 1, "title": "stale"},
        {"ts": "not-a-number", "title": "broken"},
        "not-a-dict",
    ])
    assert [item["title"] for item in common.load_recent_news()] == ["fresh"]


def test_load_recent_news_caps_the_item_count(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "NEWS_CONTEXT_FILE", tmp_path / "recent.json")
    now = time.time()
    common.save_recent_news([{"ts": now, "title": str(i)} for i in range(common.CONTEXT_MAX_ITEMS + 20)])
    loaded = common.load_recent_news()
    assert len(loaded) == common.CONTEXT_MAX_ITEMS
    assert loaded[-1]["title"] == str(common.CONTEXT_MAX_ITEMS + 19)


def test_load_recent_news_tolerates_a_missing_or_broken_file(tmp_path, monkeypatch):
    missing = tmp_path / "missing.json"
    monkeypatch.setattr(common, "NEWS_CONTEXT_FILE", missing)
    assert common.load_recent_news() == []

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(common, "NEWS_CONTEXT_FILE", broken)
    assert common.load_recent_news() == []

    wrong_shape = tmp_path / "wrong.json"
    wrong_shape.write_text('{"a": 1}', encoding="utf-8")
    monkeypatch.setattr(common, "NEWS_CONTEXT_FILE", wrong_shape)
    assert common.load_recent_news() == []


def test_save_recent_news_replaces_atomically(tmp_path, monkeypatch):
    target = tmp_path / "recent.json"
    monkeypatch.setattr(common, "NEWS_CONTEXT_FILE", target)
    common.save_recent_news([{"ts": time.time(), "title": "one"}])
    common.save_recent_news([{"ts": time.time(), "title": "two"}])
    assert [item["title"] for item in common.load_recent_news()] == ["two"]
    assert list(tmp_path.glob("*.tmp")) == []
