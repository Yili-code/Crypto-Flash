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

    assert "服務需要處理" in rendered
    assert "YouTube：1 部影片待完成" in rendered
    assert "新聞：1 則消息待整理" in rendered
    assert "AI 服務設定有誤" in rendered
    assert "model_configuration" not in rendered


def test_stale_block_from_old_configuration_is_not_current(monkeypatch):
    gemini_policy.write_state("youtube", {
        "day": "2026-10-09", "used": 1, "config": "old", "failures": 0,
        "retry_at": 0, "last_error": "authentication", "blocked": True, "rejected": [],
    })
    assert health.current_scope_block("youtube") == ""


def test_healthy_snapshot_does_not_print_zero_counters_or_claim_connectivity(monkeypatch):
    monkeypatch.setattr(health, "collect_health", lambda: ([], {}))
    text = health.render_health_html()
    assert text == "<b>服務檢查</b>\n目前未發現異常。"
    assert "連線正常" not in text


def test_health_preserves_critical_failures_without_exposing_internal_paths(monkeypatch):
    issues = [health.HealthIssue("critical", "live", "cannot read private/path/state.json")]
    monkeypatch.setattr(health, "collect_health", lambda: (issues, {}))
    text = health.render_health_html()
    assert "服務需要處理" in text and "狀態資料無法讀取" in text
    assert "private/path" not in text
