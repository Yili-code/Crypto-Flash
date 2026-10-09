import json

import gemini
import gemini_policy
import operational_health as health
import classification_backlog


def test_health_reports_current_block_and_pending_work(tmp_path, monkeypatch):
    monkeypatch.setattr(health, "STATE_DIR", tmp_path)
    monkeypatch.setattr(classification_backlog, "BACKLOG_FILE", tmp_path / "classification_backlog.json")
    monkeypatch.setenv("TELEGRAM_OWNER_USER_IDS", "123")
    (tmp_path / "yt_progress.json").write_text(json.dumps({
        "video": {"research_delivered": False},
    }), encoding="utf-8")
    classification_backlog.enqueue({"id": "one", "data": {"content": "BTC"}})
    gemini_policy.write_state("youtube", {
        "day": "2026-10-09", "used": 1, "config": gemini.current_config_id(), "failures": 0,
        "retry_at": 0, "last_error": "model_configuration", "blocked": True, "rejected": [],
    })

    rendered = health.render_health_html()

    assert "CRITICAL" in rendered
    assert "YouTube pending 1" in rendered
    assert "Flash classification pending 1" in rendered


def test_stale_block_from_old_configuration_is_not_current(monkeypatch):
    gemini_policy.write_state("youtube", {
        "day": "2026-10-09", "used": 1, "config": "old", "failures": 0,
        "retry_at": 0, "last_error": "authentication", "blocked": True, "rejected": [],
    })
    assert health.current_scope_block("youtube") == ""
