import asyncio
import json
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import aiohttp
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
    assert "09/16 02:00  FOMC Rate Decision" in text
    assert "09/16 20:30  CPI" in text
    assert "09/17 02:00  Nonfarm Payrolls" in text


def test_winter_offset_and_midnight_boundaries():
    rows = [entry("2026-01-13T10:59:59-05:00", "CPI y/y"),
            entry("2026-01-13T11:00:00-05:00", "CPI m/m"),
            entry("2026-01-15T10:59:59-05:00", "Non-Farm Employment Change"),
            entry("2026-01-15T11:00:00-05:00", "FOMC Statement")]
    assert [name for _, name in ec.select_events(rows, date(2026, 1, 14))] == ["CPI", "非農就業"]


def test_no_events_explains_dates_scope_and_meaning():
    text = ec.render_messages(ec.select_events([entry(title="Retail Sales m/m")], date(2026, 9, 16)),
                              date(2026, 9, 16))[0]
    assert "2026/09/16–09/17" in text
    assert "No CPI, nonfarm payrolls, or FOMC events scheduled for these two days." in text
    assert "https://www.forexfactory.com/calendar" in text


def test_two_day_summer_boundaries():
    rows = [entry("2026-09-15T11:59:59-04:00", "CPI y/y"),
            entry("2026-09-15T12:00:00-04:00", "CPI m/m"),
            entry("2026-09-16T12:00:00-04:00", "Non-Farm Employment Change"),
            entry("2026-09-17T11:59:59-04:00", "FOMC Statement"),
            entry("2026-09-17T12:00:00-04:00", "FOMC Press Conference")]
    assert [name for _, name in ec.select_events(rows, date(2026, 9, 16))] == [
        "CPI", "非農就業", "FOMC 利率決議"]


@pytest.mark.parametrize("rows", [[], {}, [None], [dict(title="CPI m/m")],
                                     [entry("2026-09-16T08:30:00")], [entry("invalid")]])
def test_bad_feed_never_means_no_events(rows):
    with pytest.raises((ValueError, TypeError)):
        ec.select_events(rows, date(2026, 9, 16))


@pytest.mark.parametrize("day", [date(2026, 9, 23), date(2026, 9, 13), date(2026, 9, 20),
                                 date(2026, 9, 19)])
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
    monkeypatch.setattr(ec, "CALENDAR_RETRY_DELAYS", (0, 0))
    sleeper = AsyncMock()
    monkeypatch.setattr(ec.asyncio, "sleep", sleeper)
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(ec, "send_telegram_message", sender)
    return sender


def test_success_saved_and_rerun_skipped(delivery):
    asyncio.run(ec.main())
    assert json.loads(ec.STATE_FILE.read_text())["last_sent_date"] == datetime.now(ec.TAIPEI).date().isoformat()
    asyncio.run(ec.main())
    delivery.assert_awaited_once()
    assert "No CPI, nonfarm payrolls, or FOMC events scheduled for these two days." in delivery.call_args.args[2]


def test_send_failure_does_not_save(delivery):
    delivery.return_value = False
    with pytest.raises(RuntimeError, match="delivery failed"):
        asyncio.run(ec.main())
    assert not ec.STATE_FILE.exists()


def test_explicit_force_resends_today_without_changing_default_dedup(delivery):
    asyncio.run(ec.main())
    asyncio.run(ec.main(force=True))
    asyncio.run(ec.main())
    assert delivery.await_count == 2


def test_fetch_failure_notifies_only_after_all_retries_and_does_not_save(delivery, monkeypatch):
    fetcher = AsyncMock(side_effect=asyncio.TimeoutError())
    monkeypatch.setattr(ec, "fetch_calendar", fetcher)
    with pytest.raises(RuntimeError, match="unavailable"):
        asyncio.run(ec.main())
    assert fetcher.await_count == 3
    assert ec.asyncio.sleep.await_count == 2
    delivery.assert_awaited_once()
    notice = delivery.call_args.args[2]
    assert "Calendar data unavailable. Reminder was not marked as delivered." in notice
    assert "Taiwan Time" in notice
    assert "資料不完整" not in notice
    assert not ec.STATE_FILE.exists()


def test_transient_fetch_failure_recovers_and_delivers(delivery, monkeypatch):
    fetcher = AsyncMock(side_effect=[asyncio.TimeoutError(), [entry()]])
    monkeypatch.setattr(ec, "fetch_calendar", fetcher)
    asyncio.run(ec.main())
    assert fetcher.await_count == 2
    ec.asyncio.sleep.assert_awaited_once_with(0)
    delivery.assert_awaited_once()
    assert json.loads(ec.STATE_FILE.read_text())["last_sent_date"] == datetime.now(ec.TAIPEI).date().isoformat()


def test_dry_run_does_not_send_or_save(delivery, capsys):
    asyncio.run(ec.main(dry_run=True))
    delivery.assert_not_awaited()
    assert not ec.STATE_FILE.exists()
    assert "No CPI, nonfarm payrolls, or FOMC events scheduled for these two days." in capsys.readouterr().out


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


def test_two_day_window_fits_before_source_week_end():
    assert ec.select_events([entry()], date(2026, 9, 18)) == []


def test_unavailable_notice_uses_two_day_range_across_year_end():
    assert "2026/12/31–2027/01/01" in ec.render_unavailable_notice(date(2026, 12, 31))


def test_feed_timezone_does_not_change_source_week():
    rows = [entry("2026-10-12T07:00:00+08:00"),
            entry("2026-10-18T08:00:00+08:00", "Retail Sales m/m")]
    assert ec.select_events(rows, date(2026, 10, 12)) == [
        (datetime.fromisoformat("2026-10-11T23:00:00+00:00"), "CPI")]
    equivalent = [dict(row, date=datetime.fromisoformat(row["date"])
                       .astimezone(ec.SOURCE_TIMEZONE).isoformat()) for row in rows]
    assert ec.select_events(rows, date(2026, 10, 12)) == ec.select_events(
        equivalent, date(2026, 10, 12))


def test_real_cross_week_window_still_rejected():
    with pytest.raises(ValueError, match="cover"):
        ec.select_events([entry("2026-10-12T07:00:00+08:00")], date(2026, 10, 17))


def test_invalid_data_is_not_repeatedly_fetched(delivery, monkeypatch):
    fetcher = AsyncMock(side_effect=ValueError("Calendar feed spans unexpected weeks"))
    monkeypatch.setattr(ec, "fetch_calendar", fetcher)
    with pytest.raises(RuntimeError, match="spans unexpected weeks"):
        asyncio.run(ec.main())
    fetcher.assert_awaited_once()
    ec.asyncio.sleep.assert_not_awaited()
    assert not ec.STATE_FILE.exists()


@pytest.mark.parametrize("retry_after, expected", [("90", 90), ("invalid", 60)])
def test_rate_limit_respects_provider_delay(delivery, monkeypatch, retry_after, expected, caplog):
    error = aiohttp.ClientResponseError(
        None, (), status=429, headers={"Retry-After": retry_after})
    monkeypatch.setattr(ec, "fetch_calendar", AsyncMock(side_effect=[error, [entry()]]))
    asyncio.run(ec.main())
    ec.asyncio.sleep.assert_awaited_once_with(expected)
    assert "HTTP 429" in caplog.text


def test_long_rate_limit_does_not_retry_early(delivery, monkeypatch):
    error = aiohttp.ClientResponseError(
        None, (), status=429, headers={"Retry-After": "600"})
    fetcher = AsyncMock(side_effect=error)
    monkeypatch.setattr(ec, "fetch_calendar", fetcher)
    with pytest.raises(RuntimeError, match="beyond retry budget"):
        asyncio.run(ec.main())
    fetcher.assert_awaited_once()
    ec.asyncio.sleep.assert_not_awaited()
    assert not ec.STATE_FILE.exists()


def range_row(title="CPI", when="2026-10-19T12:30:00Z", country="US"):
    return dict(title=title, date=when, country=country)


def test_range_calendar_crosses_week_and_deduplicates_releases():
    rows = [range_row(), range_row("Core Inflation Rate MoM"),
            range_row("Non Farm Payrolls"), range_row("Nonfarm Payrolls Private"),
            range_row("FOMC Minutes"), range_row("Fed Interest Rate Decision")]
    events = ec.select_range_events(dict(status="ok", result=rows), date(2026, 10, 18))
    assert {label for _, label in events} == {"CPI", "非農就業", "FOMC 利率決議"}
    assert len(events) == 3


@pytest.mark.parametrize("payload", [{}, {"status": "error", "result": []},
    {"status": "ok", "result": None}, {"status": "ok", "result": [{}]},
    {"status": "ok", "result": [range_row(when="2026-10-17T15:59:59Z")]},
    {"status": "ok", "result": [range_row(when="2026-10-19T16:00:00Z")]},
    {"status": "ok", "result": [range_row(when="2026-10-19T12:30:00")]},
    {"status": "ok", "result": [range_row(country="GB")]}])
def test_range_invalid_or_wrong_window_never_means_no_events(payload):
    with pytest.raises(ValueError):
        ec.select_range_events(payload, date(2026, 10, 18))


def test_range_empty_success_and_window_identity():
    payload = {"day": "2026-10-18", "range_events": dict(status="ok", result=[])}
    assert ec.select_events(payload, date(2026, 10, 18)) == []
    with pytest.raises(ValueError, match="different"):
        ec.select_events(payload, date(2026, 10, 19))


FED_MONTH = '''October 2026 FOMC Meetings <div class="panel-body">
<div class="col-xs-2"><p>2:30 p.m.</p></div>
<div class="col-xs-7"><p>FOMC Press Conference</p></div>
<div class="col-xs-3"><p>28</p></div>'''


def test_official_press_conference_uses_new_york_time():
    rows = ec.fed_events(FED_MONTH, 2026, 10)
    events = ec.select_range_events(dict(status="ok", result=rows), date(2026, 10, 29))
    assert events == [(datetime.fromisoformat("2026-10-28T18:30:00+00:00"), "FOMC 記者會")]
    with pytest.raises(ValueError):
        ec.fed_events(FED_MONTH, 2026, 11)
    with pytest.raises(ValueError):
        ec.fed_events(FED_MONTH.replace("2:30 p.m.", "Tentative"), 2026, 10)


def test_projection_dates_require_official_markers():
    html = '''2026 FOMC Meetings
    <div class="fomc-meeting__month"><strong>December</strong></div>
    <div class="fomc-meeting__date">8-9*</div>
    * Meeting associated with a Summary of Economic Projections.
    2027 FOMC Meetings'''
    assert ec.projection_dates(html, 2026) == {date(2026, 12, 9)}
    with pytest.raises(ValueError):
        ec.projection_dates(html, 2027)


def test_live_fetch_falls_back_when_weekly_feed_is_stale(monkeypatch):
    session = MagicMock()
    def reply(payload=None, html=None, error=None):
        response = MagicMock()
        response.raise_for_status.side_effect = error
        response.json = AsyncMock(return_value=payload)
        response.text = AsyncMock(return_value=html)
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=response)
        context.__aexit__ = AsyncMock(return_value=False)
        return context
    # The source transport succeeds, but the weekly data is unusably old.
    # Freeze today so the requested UTC interval and Fed month are deterministic.
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 18, 8, tzinfo=ec.TAIPEI)
    monkeypatch.setattr(ec, "datetime", Clock)
    session.get.side_effect = [reply([entry("2020-01-01T08:30:00-05:00")]),
                              reply(dict(status="ok", result=[])),
                              reply(html="October 2026 FOMC Meetings")]
    result = asyncio.run(ec.fetch_calendar(session))
    assert ec.select_events(result, date(2026, 10, 18)) == []
    params = session.get.call_args_list[1].kwargs["params"]
    assert params == {"from": "2026-10-17T16:00:00Z", "to": "2026-10-19T15:59:59.999000Z", "countries": "US"}
    assert session.get.call_count == 3
