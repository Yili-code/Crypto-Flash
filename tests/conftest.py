import pytest

import tg


@pytest.fixture(autouse=True)
def _no_send_throttle(monkeypatch):
    """Real sends are deliberately spaced seconds apart; tests must not pay for that."""
    monkeypatch.setattr(tg, "SEND_MIN_INTERVAL", 0.0)


@pytest.fixture(autouse=True)
def _pinned_credentials(monkeypatch):
    """common.py loads the developer's .env at import time. Pin the values these modules
    captured so the suite behaves the same locally and on a bare CI runner."""
    monkeypatch.setattr(tg, "TELEGRAM_BOT_TOKEN_01", "token-01")
    monkeypatch.setattr(tg, "TELEGRAM_BOT_TOKEN_02", "token-02")
    monkeypatch.setattr(tg, "TELEGRAM_CHAT_ID", "-100test")
