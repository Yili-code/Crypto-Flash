import time

import pytest

import common
import telegram_assistant as qa


# ─── who is talking to the bot ─────────────────────────────────────────────────

def test_a_mention_is_stripped_from_the_question():
    assert qa.extract_question("@jarvis_bot BTC 走勢?", "jarvis_bot", "group") == "BTC 走勢?"


def test_a_mention_is_matched_case_insensitively():
    assert qa.extract_question("@JARVIS_BOT hello", "jarvis_bot", "group") == "hello"


def test_a_bare_mention_is_not_a_question():
    assert qa.extract_question("@jarvis_bot", "jarvis_bot", "group") is None


def test_the_ask_command_works_without_a_known_bot_username():
    assert qa.extract_question("/ask BTC?", "", "group") == "BTC?"


def test_group_chatter_without_a_mention_is_ignored():
    assert qa.extract_question("random talk", "jarvis_bot", "group") is None


def test_private_messages_are_treated_as_questions():
    assert qa.extract_question("BTC?", "jarvis_bot", "private") == "BTC?"


def test_start_help_and_blank_messages_are_ignored():
    for text in ("/start", "/help me", "", "   ", None):
        assert qa.extract_question(text, "jarvis_bot", "private") is None


# ─── the context handed to Gemini ──────────────────────────────────────────────

@pytest.mark.parametrize("text,username,expected", [
    ("/ask@jarvis_bot BTC?", "jarvis_bot", "BTC?"),
    ("/ask@JARVIS_BOT BTC?", "jarvis_bot", "BTC?"),
    ("/ask@jarvis_bot", "jarvis_bot", None),
    ("/ask@other_bot BTC?", "jarvis_bot", None),
    ("/ask@other_bot BTC?", "", None),
    ("/asking BTC?", "jarvis_bot", None),
    ("@jarvis_bot_extra BTC?", "jarvis_bot", None),
    ("hello@jarvis_bot BTC?", "jarvis_bot", None),
])
def test_question_routing_respects_commands_and_username_boundaries(text, username, expected):
    assert qa.extract_question(text, username, "group") == expected


def test_context_snippet_reports_when_there_is_nothing_to_show(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "NEWS_CONTEXT_FILE", tmp_path / "missing.json")
    assert "no recent flash-news record" in qa.build_context_snippet()


def test_context_snippet_formats_one_line_per_item(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "NEWS_CONTEXT_FILE", tmp_path / "recent.json")
    now = time.time()
    common.save_recent_news([{"ts": now, "title": "美联储降息", "content": "", "tier": "HIGH"}])
    line = qa.build_context_snippet()
    assert "(HIGH)" in line
    assert "美联储降息" in line
    assert time.strftime("%H:%M", time.localtime(now)) in line


def test_context_snippet_honours_the_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "NEWS_CONTEXT_FILE", tmp_path / "recent.json")
    now = time.time()
    common.save_recent_news([{"ts": now, "title": f"t{i}", "content": "", "tier": "LOW"} for i in range(5)])
    lines = qa.build_context_snippet(limit=2).splitlines()
    assert len(lines) == 2
    assert "t4" in lines[-1]


def test_context_snippet_falls_back_to_the_content_when_there_is_no_title(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "NEWS_CONTEXT_FILE", tmp_path / "recent.json")
    common.save_recent_news([{"ts": time.time(), "title": "", "content": "body text", "tier": None}])
    snippet = qa.build_context_snippet()
    assert "body text" in snippet
    assert "(-)" in snippet
