import jin10_monitor as jm


def test_clean_html_converts_breaks_strips_tags_and_unescapes():
    assert jm.clean_html("a<br/>b<b>c</b>&amp;d") == "a\nbc&d"


def test_item_text_prefers_the_structured_fields():
    item = {"data": {"title": "美联储降息", "content": "比特币上涨"}}
    assert jm.item_text(item) == ("美联储降息", "比特币上涨")


def test_item_text_falls_back_to_the_bracketed_title():
    item = {"data": {"content": "<b>【美联储降息】</b>比特币上涨"}}
    assert jm.item_text(item) == ("美联储降息", "比特币上涨")


def test_item_text_falls_back_to_indicator_data():
    item = {"type": 1, "data": {
        "name": "CPI", "time_period": "8月", "measure": "年率",
        "actual": "3.1", "unit": "%", "consensus": "3.0", "previous": "2.9", "country": "美国",
    }}
    title, content = jm.item_text(item)
    assert title == "CPI 8月 年率"
    assert "Actual: 3.1%" in content
    assert "Expected: 3.0%" in content
    assert "Previous: 2.9%" in content
    assert "Market: 美国" in content


def test_item_text_returns_blanks_for_an_empty_item():
    assert jm.item_text({}) == ("", "")


def test_indicator_item_text_ignores_non_indicator_items():
    assert jm.indicator_item_text({"type": 2, "data": {"name": "CPI"}}) == ("", "")


def test_item_data_rejects_a_non_object_payload():
    assert jm.item_data({"data": "oops"}) == {}


def test_clean_number_treats_null_placeholders_as_empty():
    assert jm.clean_number(None) == ""
    assert jm.clean_number("null") == ""
    assert jm.clean_number("None") == ""
    assert jm.clean_number("  ") == ""
    assert jm.clean_number(0) == "0"


def test_match_keywords_hits_and_misses(monkeypatch):
    monkeypatch.setattr(jm, "KEYWORDS", ["比特币", "ETF"])
    assert jm.match_keywords("比特币暴涨")
    assert not jm.match_keywords("天气晴朗")


def test_match_keywords_passes_everything_when_unconfigured(monkeypatch):
    monkeypatch.setattr(jm, "KEYWORDS", [])
    assert jm.match_keywords("anything at all")


def test_load_keywords_falls_back_when_the_file_is_unreadable(monkeypatch):
    monkeypatch.setenv("KEYWORDS_FILE", "does/not/exist.txt")
    assert jm.load_keywords("KEYWORDS_FILE", ["fallback"]) == ["fallback"]


def test_load_keywords_reads_a_file_and_skips_comments(tmp_path, monkeypatch):
    path = tmp_path / "kw.txt"
    path.write_text("# comment\n比特币\n\n  ETF  \n", encoding="utf-8")
    monkeypatch.setenv("KEYWORDS_FILE", str(path))
    assert jm.load_keywords("KEYWORDS_FILE", ["fallback"]) == ["比特币", "ETF"]


def test_format_message_prefixes_only_the_badged_tiers():
    assert jm.format_message("body", "CRITICAL") == "CRITICAL\nbody"
    assert jm.format_message("body", "LOW") == "body"
    assert jm.format_message("body", None) == "body"


def test_is_new_dedupes_by_id(monkeypatch):
    monkeypatch.setattr(jm, "seen_ids", {})
    assert jm.is_new({"id": "1"})
    assert not jm.is_new({"id": "1"})


def test_is_new_rejects_items_without_an_id(monkeypatch):
    monkeypatch.setattr(jm, "seen_ids", {})
    assert not jm.is_new({})


def test_is_new_evicts_so_the_cache_stays_bounded(monkeypatch):
    monkeypatch.setattr(jm, "seen_ids", {})
    for i in range(2100):
        jm.is_new({"id": f"x{i}"})
    assert len(jm.seen_ids) <= 2000
    assert jm.is_new({"id": "x0"})  # the oldest ids were evicted, so they look new again
