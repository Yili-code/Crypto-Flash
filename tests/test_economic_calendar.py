import asyncio
import json
from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest

import economic_calendar as ec


def entry(when="2026-09-16T08:30:00-04:00", title="CPI m/m", country="USD", impact="High"):
    return dict(date=when, title=title, country=country, impact=impact)


def test_taiwan_day_filter_sort_deduplicate_and_utc_rollover():
    rows = [entry(), entry(), entry("2026-09-15T14:00:00-04:00", "FOMC Statement"),
            entry("2026-09-16T14:00:00-04:00", "Non-Farm Employment Change"),
            entry(country="GBP"), entry(title="Retail Sales m/m")]
    events = ec.select_events(rows, date(2026, 9, 16))
    assert [title for _, title in events] == ["FOMC 利率決議", "CPI", "非農就業"]
    text = ec.render_messages(events, date(2026, 9, 16))[0]
    assert "09/16 02:00  FOMC 利率決議" in text
    assert "09/16 20:30  CPI" in text
    assert "09/17 02:00  非農就業" in text


def test_winter_offset_and_midnight_boundaries():
    rows = [entry("2026-01-13T10:59:59-05:00", "CPI y/y"),
            entry("2026-01-13T11:00:00-05:00", "CPI m/m"),
            entry("2026-01-16T10:59:59-05:00", "Non-Farm Employment Change"),
            entry("2026-01-16T11:00:00-05:00", "FOMC Statement")]
    assert [name for _, name in ec.select_events(rows, date(2026, 1, 14))] == ["CPI", "非農就業"]


def test_no_events_explains_dates_scope_and_meaning():
    text = ec.render_messages(ec.select_events([entry(title="Retail Sales m/m")], date(2026, 9, 16)),
                              date(2026, 9, 16))[0]
    assert "2026/09/16–09/18" in text
    assert "這三天沒有 CPI、非農或 FOMC" in text
    assert "https://www.forexfactory.com/calendar" in text


def test_three_day_summer_boundaries():
    rows = [entry("2026-09-15T11:59:59-04:00", "CPI y/y"),
            entry("2026-09-15T12:00:00-04:00", "CPI m/m"),
            entry("2026-09-16T12:00:00-04:00", "Non-Farm Employment Change"),
            entry("2026-09-18T11:59:59-04:00", "FOMC Statement"),
            entry("2026-09-18T12:00:00-04:00", "FOMC Press Conference")]
    assert [name for _, name in ec.select_events(rows, date(2026, 9, 16))] == [
        "CPI", "非農就業", "FOMC 利率決議"]


@pytest.mark.parametrize("rows", [[], {}, [None], [dict(title="CPI m/m")],
                                     [entry("2026-09-16T08:30:00")], [entry("invalid")]])
def test_bad_feed_never_means_no_events(rows):
    with pytest.raises((ValueError, TypeError)):
        ec.select_events(rows, date(2026, 9, 16))


@pytest.mark.parametrize("day", [date(2026, 9, 23), date(2026, 9, 13), date(2026, 9, 20),
                                 date(2026, 9, 18), date(2026, 9, 19)])
def test_stale_or_partial_week_rejected(day):
    with pytest.raises(ValueError, match="cover"):
        ec.select_events([entry()], day)


def test_escape_and_split_without_losing_events():
    events = [(datetime.fromisoformat("2026-09-16T12:30:00+00:00"), f"Event {i} <&> " + "數" * 100)
              for i in range(50)]
    messages = ec.render_messages(events, date(2026, 9, 16))
    assert len(messages) > 1
    assert all(len(message.encode("utf-16-le")) // 2 <= 4000 for message in messages)
    assert sum(message.count("&lt;&amp;&gt;") for message in messages) == 50


@pytest.fixture
def delivery(tmp_path, monkeypatch):
    monkeypatch.setattr(ec, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(ec, "fetch_calendar", AsyncMock(return_value=[entry()]))
    monkeypatch.setattr(ec, "select_events", lambda payload, day: [])
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(ec, "send_telegram_message", sender)
    return sender


def test_success_saved_and_rerun_skipped(delivery):
    asyncio.run(ec.main())
    assert json.loads(ec.STATE_FILE.read_text())["last_sent_date"] == datetime.now(ec.TAIPEI).date().isoformat()
    asyncio.run(ec.main())
    delivery.assert_awaited_once()
    assert "這三天沒有 CPI、非農或 FOMC" in delivery.call_args.args[2]


def test_send_failure_does_not_save(delivery):
    delivery.return_value = False
    with pytest.raises(RuntimeError, match="delivery failed"):
        asyncio.run(ec.main())
    assert not ec.STATE_FILE.exists()


def test_fetch_failure_sends_unavailable_not_none(delivery, monkeypatch):
    monkeypatch.setattr(ec, "fetch_calendar", AsyncMock(side_effect=ValueError("bad feed")))
    with pytest.raises(RuntimeError, match="unavailable"):
        asyncio.run(ec.main())
    assert "不能判定" in delivery.call_args.args[2]
    assert not ec.STATE_FILE.exists()


def test_dry_run_does_not_send_or_save(delivery, capsys):
    asyncio.run(ec.main(dry_run=True))
    delivery.assert_not_awaited()
    assert not ec.STATE_FILE.exists()
    assert "這三天沒有 CPI、非農或 FOMC" in capsys.readouterr().out


def test_corrupt_state_stops_before_send(delivery):
    ec.STATE_FILE.write_text("invalid")
    with pytest.raises(ValueError):
        asyncio.run(ec.main())
    delivery.assert_not_awaited()


def test_only_requested_events_and_same_release_deduplicated():
    rows = [entry(title=title, impact="Medium") for title in ec.EVENT_LABELS]
    rows += [entry(title=title) for title in ["FOMC Meeting Minutes", "FOMC Member Williams Speaks", "PPI m/m", "Unemployment Rate", "ADP Non-Farm Employment Change"]]
    rows += [entry(country="CAD")]
    events = ec.select_events(rows, date(2026, 9, 16))
    assert {title for _, title in events} == {"CPI", "非農就業", "FOMC 利率決議", "FOMC 記者會", "FOMC 經濟預測"}
    assert len(events) == 5
