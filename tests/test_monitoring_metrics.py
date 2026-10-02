import json

import monitoring_metrics as mm


def test_daily_metrics_records_funnel_delivery_latency_and_queue(tmp_path, monkeypatch):
    clock = iter([100.0, 100.2, 100.5])
    monkeypatch.setattr(mm.time, "time", lambda: next(clock))
    recorder = mm.DailyMetrics(tmp_path / "monitoring.json")
    item = {}

    recorder.observe_received(item)
    recorder.increment("keyword_filter_passed")
    recorder.observe_queue_size(1)
    recorder.observe_queue_size(3)
    recorder.observe_queue_size(2)
    recorder.record_push("HIGH", item[mm.RECEIVED_AT_KEY])
    recorder.record_push("CRITICAL", 100.0)

    day = next(iter(json.loads(recorder.path.read_text(encoding="utf-8"))["days"].values()))
    assert day["received_events"] == 1
    assert day["keyword_filter_passed"] == 1
    assert day["pushes"] == {
        "total": 2,
        "importance": {"CRITICAL": 1, "HIGH": 1, "LOW": 0, "MEDIUM": 0},
    }
    assert day["latency_ms"] == {"sample_count": 2, "p50": 350, "p95": 485}
    assert day["queue_high_water_mark"] == 3


def test_observe_received_only_counts_an_item_once(tmp_path):
    recorder = mm.DailyMetrics(tmp_path / "monitoring.json")
    item = {}
    recorder.observe_received(item)
    recorder.observe_received(item)

    day = next(iter(json.loads(recorder.path.read_text(encoding="utf-8"))["days"].values()))
    assert day["received_events"] == 1


def test_retention_keeps_only_latest_days(tmp_path):
    path = tmp_path / "monitoring.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "timezone": "Asia/Taipei",
        "days": {"2026-01-01": {}, "2026-01-02": {}, "2099-01-01": {}},
    }), encoding="utf-8")
    recorder = mm.DailyMetrics(path, retention_days=2)
    recorder.increment("received_events")

    days = json.loads(path.read_text(encoding="utf-8"))["days"]
    assert len(days) == 2
    assert "2026-01-01" not in days
    assert "2026-01-02" not in days
    assert "2099-01-01" in days
