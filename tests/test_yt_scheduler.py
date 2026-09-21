import asyncio
from unittest.mock import AsyncMock

import pytest

import yt_monitor as yt
from test_yt_monitor import FEED, channel_cfg


@pytest.fixture
def scheduler(tmp_path, monkeypatch):
    monkeypatch.setattr(yt, 'SEEN_STATE_FILE', tmp_path / 'seen.json')
    configs = [channel_cfg(name=name, channel_id='UC' + name, max_new_per_run=2) for name in ('A', 'B', 'C')]
    seen = {cfg['name']: ['seed'] for cfg in configs}
    yt.save_seen_state(seen)
    events = []
    async def fetch(session, url):
        events.append(('feed', url.rsplit('=', 1)[-1]))
        return FEED
    async def process(session, cfg, record, progress):
        events.append((cfg['name'], record['video_id']))
        record.update(summary='s', research='r', summary_completed=True, research_completed=True,
                      notified=True, summary_delivered=True, research_delivered=True)
        yt.save_progress(progress)
    monkeypatch.setattr(yt, 'fetch_feed', fetch)
    monkeypatch.setattr(yt, 'process_video', process)
    monkeypatch.setattr(yt, 'check_chat_access', AsyncMock(return_value=True))
    return configs, seen, events


def test_all_feeds_saved_before_round_robin_processing(scheduler):
    configs, seen, events = scheduler
    asyncio.run(yt.run_channels(None, configs, seen))
    assert events == [('feed', 'UCA'), ('feed', 'UCB'), ('feed', 'UCC'),
                      ('A', 'older'), ('B', 'older'), ('C', 'older'),
                      ('A', 'newest'), ('B', 'newest'), ('C', 'newest')]
    assert yt.load_schedule() == 'UCB'
    assert all(r['research_delivered'] for r in yt.load_progress().values())


def test_different_channel_limits_do_not_block_other_channels(scheduler):
    configs, seen, events = scheduler
    configs[0]['max_new_per_run'] = 1
    asyncio.run(yt.run_channels(None, configs, seen))
    assert events[3:] == [('A', 'older'), ('B', 'older'), ('C', 'older'), ('B', 'newest'), ('C', 'newest')]
    assert not yt.load_progress()['UCA:newest']['notified']
    assert 'newest' not in yt.load_seen_state()['A']


def test_interruption_persists_all_backlogs_and_next_channel(scheduler, monkeypatch):
    configs, seen, events = scheduler
    async def interrupted(*args):
        raise asyncio.CancelledError
    monkeypatch.setattr(yt, 'process_video', interrupted)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(yt.run_channels(None, configs, seen))
    assert len(yt.load_progress()) == 6
    assert yt.load_schedule() == 'UCB'
    order = []
    async def resume(session, cfg, record, progress):
        order.append(cfg['name'])
    monkeypatch.setattr(yt, 'process_video', resume)
    monkeypatch.setattr(yt, 'fetch_feed', AsyncMock(return_value=None))
    asyncio.run(yt.run_channels(None, configs, yt.load_seen_state()))
    assert order == ['B', 'C', 'A', 'B', 'C', 'A']


def test_completed_pass_rotates_start_even_if_all_requests_are_deferred(scheduler, monkeypatch):
    configs, seen, _ = scheduler
    order = []
    async def deferred(session, cfg, record, progress):
        order.append(cfg['name'])
    monkeypatch.setattr(yt, 'process_video', deferred)
    asyncio.run(yt.run_channels(None, configs, seen))
    order.clear()
    asyncio.run(yt.run_channels(None, configs, yt.load_seen_state()))
    assert order == ['B', 'C', 'A', 'B', 'C', 'A']
    assert yt.load_schedule() == 'UCC'


def test_unavailable_telegram_still_saves_all_new_videos(scheduler, monkeypatch):
    configs, seen, events = scheduler
    monkeypatch.setattr(yt, 'check_chat_access', AsyncMock(return_value=False))
    asyncio.run(yt.run_channels(None, configs, seen))
    assert len(events) == 3
    assert len(yt.load_progress()) == 6
    assert all(not r['notified'] for r in yt.load_progress().values())


def test_time_budget_keeps_remaining_work_and_resumes_next_channel(scheduler, monkeypatch):
    configs, seen, _ = scheduler
    calls = []
    async def too_slow(session, cfg, record, progress):
        calls.append(cfg['name'])
        await asyncio.Event().wait()
    monkeypatch.setattr(yt, 'RUN_BUDGET_SECONDS', 1.0)
    monkeypatch.setattr(yt, 'process_video', too_slow)
    asyncio.run(yt.run_channels(None, configs, seen))
    assert calls == ['A']
    assert yt.load_schedule() == 'UCB'
    assert len(yt.load_progress()) == 6


def test_one_video_failure_does_not_block_other_channels(scheduler, monkeypatch):
    configs, seen, _ = scheduler
    order = []
    async def broken(session, cfg, record, progress):
        order.append(cfg['name'])
        if cfg['name'] == 'A':
            raise RuntimeError('video unavailable')
    monkeypatch.setattr(yt, 'process_video', broken)
    asyncio.run(yt.run_channels(None, configs, seen))
    assert order == ['A', 'B', 'C', 'A', 'B', 'C']


def test_cursor_handles_removed_channel(scheduler):
    configs, seen, events = scheduler
    yt.save_schedule('UCremoved')
    asyncio.run(yt.run_channels(None, configs, seen))
    assert events[3] == ('A', 'older')


def test_broken_cursor_fails_before_network(scheduler):
    configs, seen, events = scheduler
    yt.SCHEDULE_FILE.write_text('{broken')
    with pytest.raises(yt.SeenStateError):
        asyncio.run(yt.run_channels(None, configs, seen))
    assert events == []


def test_expired_deadline_preserves_unattempted_channel(scheduler, monkeypatch):
    configs, seen, events = scheduler
    monkeypatch.setattr(yt, 'RUN_BUDGET_SECONDS', 0)
    yt.save_schedule('UCC')
    asyncio.run(yt.run_channels(None, configs, seen))
    assert len(events) == 3
    assert yt.load_schedule() == 'UCC'
    assert all(not r['notified'] for r in yt.load_progress().values())


def test_integrated_backlog_drains_across_runs_after_feed_disappears(tmp_path, monkeypatch):
    monkeypatch.setattr(yt, 'SEEN_STATE_FILE', tmp_path / 'seen.json')
    configs = [channel_cfg(name=n, channel_id='UC' + n, max_new_per_run=3) for n in ('A', 'B', 'C')]
    seen = {c['name']: ['seed'] for c in configs}
    entries = [{'video_id': str(i), 'title': f'Video {i}', 'link': f'https://youtu.be/{i}',
                'published': '2026-09-21T00:00:00Z'} for i in range(7)]
    fetch = AsyncMock(return_value=FEED)
    summary = AsyncMock(return_value='summary')
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(yt, 'fetch_feed', fetch)
    monkeypatch.setattr(yt, 'parse_feed', lambda xml: ('channel', entries))
    monkeypatch.setattr(yt, 'summarize_video', summary)
    monkeypatch.setattr(yt, 'research_video', AsyncMock(return_value='research'))
    monkeypatch.setattr(yt, 'send_telegram_message', send)
    monkeypatch.setattr(yt, 'check_chat_access', AsyncMock(return_value=True))
    asyncio.run(yt.run_channels(None, configs, seen))
    assert len(yt.load_progress()) == 21
    assert sum(r['research_delivered'] for r in yt.load_progress().values()) == 9
    assert all(len(ids) == 4 for ids in yt.load_seen_state().values())
    fetch.return_value = None
    asyncio.run(yt.run_channels(None, configs, yt.load_seen_state()))
    assert sum(r['research_delivered'] for r in yt.load_progress().values()) == 18
    asyncio.run(yt.run_channels(None, configs, yt.load_seen_state()))
    assert all(r['research_delivered'] for r in yt.load_progress().values())
    assert summary.await_count == send.await_count == 21
    asyncio.run(yt.run_channels(None, configs, yt.load_seen_state()))
    assert summary.await_count == send.await_count == 21
