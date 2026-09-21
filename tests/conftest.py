import pytest

import tg
import yt_monitor
import gemini_policy


@pytest.fixture(autouse=True)
def _isolated_youtube_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(yt_monitor, "PROGRESS_FILE", tmp_path / "yt_progress.json")
    monkeypatch.setattr(yt_monitor, "SCHEDULE_FILE", tmp_path / "yt_schedule.json")
    monkeypatch.setenv("GEMINI_YOUTUBE_USAGE_FILE", str(tmp_path / "youtube_usage.json"))
    monkeypatch.setenv("GEMINI_LIVE_USAGE_FILE", str(tmp_path / "live_usage.json"))
    monkeypatch.setenv("GEMINI_YOUTUBE_DAILY_REQUESTS", "120")
    monkeypatch.setenv("GEMINI_LIVE_DAILY_REQUESTS", "600")
    monkeypatch.setattr(gemini_policy.random, "uniform", lambda a, b: 1.0)


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
