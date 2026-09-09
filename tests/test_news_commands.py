import asyncio
import time
from unittest.mock import AsyncMock

import pytest

import news_commands as nc
import telegram_assistant as qa
from fakes import FakeResponse


@pytest.fixture
def news(monkeypatch):
    now = time.time()
    items = [
        {"ts": now - 90, "title": "Older BTC", "content": "Spot ETF inflows", "tier": "CRITICAL"},
        {"ts": now - 10, "title": "Latest ETH", "content": "Ethereum update", "tier": "MEDIUM"},
        {"ts": now - 60, "title": "Fed", "content": "BTC liquidity", "tier": "HIGH"},
        {"ts": now - 30, "title": "Unclassified", "content": "", "tier": None},
    ]
    monkeypatch.setattr(nc, "load_recent_news", lambda: items)
    return items


def test_news_is_sorted_by_time_and_respects_limit(news):
    reply = nc.local_command_reply("/news 2", "bot")
    assert "顯示 2 / 4" in reply
    assert reply.index("Latest ETH") < reply.index("Unclassified")
    assert "Older BTC" not in reply


def test_search_matches_title_and_content_case_insensitively(news):
    reply = nc.local_command_reply("/search bTc", "bot")
    assert "Older BTC" in reply and "Fed" in reply
    assert "Latest ETH" not in reply
    assert "Older BTC" in nc.local_command_reply("/search spot ETF", "bot")


def test_important_only_includes_high_and_critical(news):
    reply = nc.local_command_reply("/important", "bot")
    assert "Older BTC" in reply and "Fed" in reply
    assert "Latest ETH" not in reply and "Unclassified" not in reply


@pytest.mark.parametrize("text", ["/news 0", "/news -1", "/news 11", "/news abc", "/news 1 2", "/search", "/status x"])
def test_bad_arguments_show_usage(text):
    assert "用法" in nc.local_command_reply(text, "bot")


def test_mentions_do_not_route_other_bots(news):
    assert nc.local_command_reply("/news@BOT", "bot") is not None
    assert nc.local_command_reply("/news@other", "bot") is None
    assert nc.local_command_reply("/news@bot", "") is None
    assert nc.local_command_reply("/newspaper", "bot") is None


def test_status_reports_snapshot_not_connection_health(news):
    reply = nc.local_command_reply("/status", "bot")
    assert "可查詢：4 則" in reply
    assert "未分級 1" in reply
    assert "不代表" in reply and "UTC+8" in reply


@pytest.mark.parametrize("pattern", ["<>&", "😀"])
def test_html_is_escaped_and_message_size_is_bounded(news, pattern):
    news[:] = [{"ts": time.time() - i, "title": pattern * 100, "content": pattern * 200, "tier": "HIGH"}
               for i in range(10)]
    reply = nc.local_command_reply("/news 10", "bot")
    assert "<>&" not in reply
    assert len(reply.encode("utf-16-le")) // 2 < 4096
    assert reply.count("<b>") == reply.count("</b>")


def test_empty_and_invalid_timestamps_are_handled(news):
    news[:] = [{"ts": ts, "title": "bad", "content": "", "tier": None}
               for ts in (float("inf"), float("nan"), True, "bad", time.time() + 100, 0)]
    assert "沒有符合" in nc.local_command_reply("/news", "bot")
    assert "尚無近期資料" in nc.local_command_reply("/status", "bot")


def test_local_commands_work_without_ai(news, monkeypatch):
    monkeypatch.setattr(qa, "GEMINI_API_KEY", "")
    model = AsyncMock()
    monkeypatch.setattr(qa, "ask_gemini_qa", model)
    for command in ("/news", "/search BTC", "/important", "/status", "/help", "/start"):
        assert asyncio.run(qa.build_reply(None, command, "bot", "group"))
    model.assert_not_awaited()


def test_ask_still_uses_gemini(monkeypatch):
    monkeypatch.setattr(qa, "GEMINI_API_KEY", "test")
    model = AsyncMock(return_value="answer")
    monkeypatch.setattr(qa, "ask_gemini_qa", model)
    assert asyncio.run(qa.build_reply(None, "/ask@bot BTC?", "bot", "group")) == "answer"
    model.assert_awaited_once_with(None, "BTC?")


def test_digest_date_routing(monkeypatch):
    monkeypatch.setattr(nc, "build_digest", lambda day: day.isoformat())
    assert nc.local_command_reply("/digest 2026-09-09", "bot") == "2026-09-09"
    assert "用法" in nc.local_command_reply("/digest 2026-02-30", "bot")
    assert nc.local_command_reply("/digest@other", "bot") is None
    assert nc.local_command_reply("/digest", "bot") == nc.previous_day().isoformat()
    assert nc.local_command_reply("/digest today", "bot") == nc.datetime.now(nc.DISPLAY_TZ).date().isoformat()


def test_listener_keeps_chat_restriction_for_new_commands(news, monkeypatch):
    monkeypatch.setattr(qa, "TELEGRAM_CHAT_ID", "allowed")
    monkeypatch.setattr(qa, "get_bot_username", AsyncMock(return_value="bot"))
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(qa, "send_telegram_message", sender)

    class Session:
        calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            if self.calls > 1:
                raise asyncio.CancelledError
            return FakeResponse(200, json_data={"result": [
                {"update_id": 1, "message": {"chat": {"id": "other", "type": "group"}, "text": "/news"}},
                {"update_id": 2, "message": {"chat": {"id": "allowed", "type": "group"},
                                              "text": "/news", "message_id": 42}},
            ]})

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(qa.telegram_assistant_loop(Session()))
    sender.assert_awaited_once()
    assert sender.call_args.args[1] == "allowed"
    assert sender.call_args.kwargs["reply_to"] == 42
