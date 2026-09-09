import asyncio
import json
import time

import pytest

import tg
from fakes import FakeResponse, FakeSession


@pytest.fixture
def no_sleep(monkeypatch):
    """Record the backoff durations instead of actually waiting them out."""
    slept: list[float] = []

    async def fake_sleep(delay):
        slept.append(delay)

    monkeypatch.setattr(tg.asyncio, "sleep", fake_sleep)
    return slept


def test_send_returns_true_on_success():
    session = FakeSession([FakeResponse(200)])
    assert asyncio.run(tg.send_telegram_message(session, "-1", "hi", "token")) is True
    assert len(session.calls) == 1
    assert session.calls[0]["json"]["parse_mode"] == "HTML"
    assert session.calls[0]["json"]["chat_id"] == "-1"


def test_send_attaches_a_reply_target_when_asked():
    session = FakeSession([FakeResponse(200)])
    asyncio.run(tg.send_telegram_message(session, "-1", "hi", "token", reply_to=7))
    assert session.calls[0]["json"]["reply_to_message_id"] == 7


def test_send_skips_entirely_when_unconfigured():
    session = FakeSession()
    assert asyncio.run(tg.send_telegram_message(session, "", "hi", "")) is False
    assert session.calls == []


def test_a_400_retries_as_plain_text_without_the_markup(no_sleep):
    session = FakeSession([FakeResponse(400, '{"ok": false}'), FakeResponse(200)])
    assert asyncio.run(tg.send_telegram_message(session, "-1", "<b>x</b> & y", "token")) is True

    first, second = session.calls
    assert first["json"]["parse_mode"] == "HTML"
    assert "parse_mode" not in second["json"]
    assert second["json"]["text"] == "x & y"


def test_a_429_backoff_is_capped(no_sleep, monkeypatch):
    # Telegram asked for 568s in production; obeying that stalled the WebSocket loop.
    monkeypatch.setattr(tg, "MAX_RETRY_AFTER", 30.0)
    body = json.dumps({"parameters": {"retry_after": 568}})
    session = FakeSession([FakeResponse(429, body), FakeResponse(200)])

    assert asyncio.run(tg.send_telegram_message(session, "-1", "hi", "token")) is True
    assert no_sleep and max(no_sleep) <= 30.0


def test_a_429_without_a_parsable_body_still_backs_off(no_sleep):
    session = FakeSession([FakeResponse(429, "not json"), FakeResponse(200)])
    assert asyncio.run(tg.send_telegram_message(session, "-1", "hi", "token")) is True


def test_send_gives_up_after_the_attempt_limit(no_sleep):
    session = FakeSession([FakeResponse(500, "boom")] * 3)
    assert asyncio.run(tg.send_telegram_message(session, "-1", "hi", "token")) is False
    assert len(session.calls) == 3


def test_send_survives_a_transport_error(no_sleep):
    class ExplodingSession(FakeSession):
        def post(self, url, **kwargs):
            raise OSError("connection reset")

    assert asyncio.run(tg.send_telegram_message(ExplodingSession(), "-1", "hi", "token")) is False


def test_throttle_spaces_consecutive_sends(monkeypatch):
    monkeypatch.setattr(tg, "SEND_MIN_INTERVAL", 0.05)
    monkeypatch.setattr(tg, "_last_send_at", 0.0)

    async def scenario():
        started = time.monotonic()
        await asyncio.gather(*(tg._throttle() for _ in range(4)))
        return time.monotonic() - started

    assert asyncio.run(scenario()) >= 0.1


def test_check_chat_access_accepts_a_reachable_chat():
    session = FakeSession([FakeResponse(200, json_data={"ok": True, "result": {"title": "g"}})])
    assert asyncio.run(tg.check_chat_access(session, "-1", "token")) is True


def test_check_chat_access_rejects_an_unreachable_chat():
    session = FakeSession([FakeResponse(400, json_data={"ok": False, "description": "chat not found"})])
    assert asyncio.run(tg.check_chat_access(session, "-1", "token")) is False


def test_check_chat_access_rejects_a_missing_configuration():
    assert asyncio.run(tg.check_chat_access(FakeSession(), "", "token")) is False
    assert asyncio.run(tg.check_chat_access(FakeSession(), "-1", "")) is False


def test_check_chat_access_does_not_treat_a_network_blip_as_misconfiguration():
    class ExplodingSession(FakeSession):
        def get(self, url, **kwargs):
            raise OSError("dns failure")

    assert asyncio.run(tg.check_chat_access(ExplodingSession(), "-1", "token")) is True


def test_strip_html_tags_leaves_the_text_behind():
    assert tg._strip_html_tags("<b>bold</b> and <i>italic</i>") == "bold and italic"


def test_an_omitted_token_uses_the_default_bot():
    session = FakeSession([FakeResponse(200)])
    assert asyncio.run(tg.send_telegram_message(session, "-1", "hi")) is True
    assert "token-01" in session.calls[0]["url"]


def test_an_explicitly_empty_token_does_not_fall_back_to_the_default_bot():
    # A missing TELEGRAM_BOT_TOKEN_02 secret must fail loudly, not push from bot 01.
    session = FakeSession([FakeResponse(200)])
    assert asyncio.run(tg.send_telegram_message(session, "-1", "hi", "")) is False
    assert session.calls == []
