import test_telegram_listener as diagnostic


def test_telegram_diagnostic_redacts_bot_token(monkeypatch):
    token = "123456:SecretToken"
    monkeypatch.setattr(diagnostic, "TELEGRAM_BOT_TOKEN_01", token)
    error = RuntimeError(f"request failed at https://api.telegram.org/bot{token}/getUpdates")
    rendered = diagnostic.safe_error(error)
    assert token not in rendered
    assert "[REDACTED]" in rendered
