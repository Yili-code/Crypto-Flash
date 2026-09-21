import asyncio
import json
import time
from unittest.mock import AsyncMock

import pytest

import yt_monitor as yt
import gemini
from fakes import FakeResponse, FakeSession
from test_yt_monitor import FEED, channel_cfg


@pytest.fixture
def flow(tmp_path, monkeypatch):
    monkeypatch.setattr(yt, 'SEEN_STATE_FILE', tmp_path / 'seen.json')
    fetch = AsyncMock(return_value=FEED)
    summary = AsyncMock(return_value='saved summary')
    research = AsyncMock(return_value='cited research')
    send = AsyncMock(return_value=True)
    for name, mock in [('fetch_feed', fetch), ('summarize_video', summary),
                       ('research_video', research), ('send_telegram_message', send)]:
        monkeypatch.setattr(yt, name, mock)
    yt.save_seen_state({'c': ['older']})
    return fetch, summary, research, send


def run():
    asyncio.run(yt.process_channel(None, channel_cfg(), yt.load_seen_state()))
    return yt.load_progress()['UC123:newest']


def test_summary_quota_failure_notifies_once_then_completes_after_restart(flow):
    fetch, summary, research, send = flow
    summary.return_value = None
    record = run()
    assert record['notified'] and not record['summary_completed'] and not record['research_completed']
    assert yt.load_seen_state()['c'] == ['older', 'newest']
    run()
    assert send.await_count == 1
    research.assert_not_awaited()
    # A new process can resume even when the old video has left the feed.
    fetch.return_value = None
    summary.return_value = 'recovered summary'
    record = run()
    assert record['summary_completed'] and record['research_completed']
    assert record['summary_delivered'] and record['research_delivered']
    assert send.await_count == 2
    assert 'recovered summary' in send.call_args.args[2]
    assert 'cited research' in send.call_args.args[2]
    run()
    assert send.await_count == 2
    assert summary.await_count == 3


def test_research_recovery_reuses_summary_and_only_sends_supplement(flow):
    _, summary, research, send = flow
    research.return_value = None
    record = run()
    assert record['summary_completed'] and record['summary_delivered']
    assert not record['research_completed']
    assert '外部查證未完成' in send.call_args.args[2]
    run()
    assert send.await_count == 1
    assert summary.await_count == 1
    research.return_value = 'recovered citation'
    record = run()
    assert record['research_completed'] and record['research_delivered']
    assert summary.await_count == 1
    assert 'recovered citation' in send.call_args.args[2]
    assert 'saved summary' not in send.call_args.args[2]


def test_generated_results_survive_telegram_failure(flow):
    _, summary, research, send = flow
    send.return_value = False
    record = run()
    assert record['summary_completed'] and record['research_completed']
    assert not record['notified']
    assert record['delivery']['next_part'] == 0
    send.return_value = True
    record = run()
    assert record['notified'] and record['research_delivered']
    assert summary.await_count == research.await_count == 1


def test_partial_message_resumes_from_saved_cursor(flow):
    _, summary, research, send = flow
    summary.return_value = 'long report ' * 1000
    send.side_effect = [True, False]
    record = run()
    parts = record['delivery']['parts']
    assert record['delivery']['next_part'] == 1
    send.side_effect = None
    send.reset_mock()
    run()
    assert [c.args[2] for c in send.call_args_list] == parts[1:]
    assert summary.await_count == research.await_count == 1


def test_pending_video_not_discarded_by_new_video_limit(flow):
    fetch, summary, _, _ = flow
    summary.return_value = None
    run()
    fetch.return_value = FEED.replace('newest', 'brand-new')
    asyncio.run(yt.process_channel(None, channel_cfg(max_new_per_run=1), yt.load_seen_state()))
    assert 'UC123:newest' in yt.load_progress()
    assert not yt.load_progress()['UC123:newest']['summary_completed']


def test_summary_saved_before_interruption_in_research(flow):
    _, summary, research, _ = flow
    research.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        run()
    assert yt.load_progress()['UC123:newest']['summary_completed']
    research.side_effect = None
    run()
    assert summary.await_count == 1


def test_broken_progress_fails_before_network(flow):
    fetch, summary, _, send = flow
    yt.PROGRESS_FILE.write_text('{broken', encoding='utf-8')
    with pytest.raises(yt.SeenStateError):
        run()
    fetch.assert_not_awaited()
    summary.assert_not_awaited()
    send.assert_not_awaited()


def test_progress_save_failure_stops_before_generation(flow, monkeypatch):
    _, summary, _, send = flow
    def fail(state):
        raise yt.SeenStateError('disk unavailable')
    monkeypatch.setattr(yt, 'save_progress', fail)
    with pytest.raises(yt.SeenStateError):
        run()
    summary.assert_not_awaited()
    send.assert_not_awaited()


def test_inconsistent_completion_is_rejected(flow):
    run()
    state = yt.load_progress()
    state['UC123:newest']['summary'] = ''
    yt.PROGRESS_FILE.write_text(json.dumps(state), encoding='utf-8')
    with pytest.raises(yt.SeenStateError):
        yt.load_progress()


def test_legacy_seen_videos_are_not_replayed(flow):
    _, summary, research, send = flow
    yt.save_seen_state({'c': ['older', 'newest']})
    asyncio.run(yt.process_channel(None, channel_cfg(), yt.load_seen_state()))
    summary.assert_not_awaited()
    research.assert_not_awaited()
    send.assert_not_awaited()


def test_integrated_api_quota_recovery_across_three_runs(tmp_path, monkeypatch):
    clock = [time.time()]
    monkeypatch.setattr(gemini.policy.time, 'time', lambda: clock[0])
    monkeypatch.setattr(yt, 'SEEN_STATE_FILE', tmp_path / 'seen.json')
    monkeypatch.setattr(yt, 'GEMINI_API_KEY', 'test')
    monkeypatch.setattr(gemini, 'GEMINI_API_KEY', 'test')
    monkeypatch.setattr(yt, 'TELEGRAM_BOT_TOKEN_02', 'test-bot')
    monkeypatch.setattr(yt, 'TELEGRAM_CHAT_ID', 'test-chat')
    yt.save_seen_state({'c': ['older']})
    def response(text, metadata=None):
        return FakeResponse(200, json_data={'candidates': [{
            'finishReason': 'STOP', 'content': {'parts': [{'text': text}]},
            'groundingMetadata': metadata or {},
        }]})
    def execute(session):
        asyncio.run(yt.process_channel(session, channel_cfg(), yt.load_seen_state()))
        return yt.load_progress()['UC123:newest']
    first = FakeSession([FakeResponse(200, FEED), FakeResponse(429, 'RESOURCE_EXHAUSTED'), FakeResponse(200)])
    record = execute(first)
    assert record['notified'] and not record['summary_completed']
    clock[0] += 31
    second = FakeSession([FakeResponse(503), response('summary'), FakeResponse(429, 'RESOURCE_EXHAUSTED'), FakeResponse(200)])
    record = execute(second)
    assert record['summary_completed'] and record['summary_delivered'] and not record['research_completed']
    clock[0] += 31
    third = FakeSession([FakeResponse(503), response('Supported claim', {
        'groundingChunks': [{'web': {'uri': 'https://example.org/data', 'title': 'Original data'}}],
        'groundingSupports': [{'segment': {'text': 'Supported claim'}, 'groundingChunkIndices': [0]}],
    }), FakeResponse(200)])
    record = execute(third)
    assert record['research_completed'] and record['research_delivered']
    assert len(third.calls) == 3
    assert third.calls[1]['json']['tools'] == [{'google_search': {}}]
    assert 'summary' not in third.calls[2]['json']['text']
    assert 'https://example.org/data' in third.calls[2]['json']['text']


def test_pending_records_survive_completed_history_pruning(flow, monkeypatch):
    _, summary, _, _ = flow
    summary.return_value = None
    run()
    state = yt.load_progress()
    finished = dict(state['UC123:newest'], summary='s', research='r', summary_completed=True,
                    research_completed=True, summary_delivered=True, research_delivered=True)
    for i in range(3):
        state[f'UC123:done{i}'] = dict(finished, video_id=f'done{i}')
    monkeypatch.setattr(yt, 'MAX_SEEN_IDS_PER_CHANNEL', 1)
    yt.save_progress(state)
    assert set(yt.load_progress()) == {'UC123:newest', 'UC123:done2'}
