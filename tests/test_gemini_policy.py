import asyncio
import json
from datetime import datetime, timezone

import pytest

import gemini
import gemini_policy as policy
from fakes import FakeResponse, FakeSession


@pytest.fixture
def clock(monkeypatch):
    now = [datetime(2026, 9, 21, 12, tzinfo=timezone.utc).timestamp()]
    monkeypatch.setattr(policy.time, 'time', lambda: now[0])
    monkeypatch.setattr(gemini, 'GEMINI_API_KEY', 'test-private-key')
    return now


def success():
    return FakeResponse(200, json_data={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': 'ok'}]}}]})


def call(session, scope='youtube', prompt='hello'):
    return asyncio.run(gemini.call_gemini(session, prompt, usage_scope=scope))


@pytest.mark.parametrize('status,data,category', [
    (429, {}, 'rate_limit'), (503, {}, 'provider_unavailable'), (500, {}, 'provider_unavailable'),
    (408, {}, 'timeout'), (401, {}, 'authentication'), (403, {}, 'authentication'),
    (404, {}, 'model_configuration'), (400, {}, 'invalid_request'),
    (400, {'error': {'details': [{'reason': 'API_KEY_INVALID'}]}}, 'authentication'),
    (400, {'error': {'status': 'FAILED_PRECONDITION'}}, 'model_configuration'),
])
def test_error_categories(status, data, category):
    assert policy.classify(status, data, {})[0] == category


def test_retry_hints_and_daily_quota(clock):
    data = {'error': {'details': [
        {'@type': 'google.rpc.RetryInfo', 'retryDelay': '123.5s'},
    ]}}
    assert policy.classify(429, data, {'Retry-After': '90'}) == ('rate_limit', 123.5)
    assert policy.classify(503, {}, {'Retry-After': 'Mon, 21 Sep 2026 12:02:00 GMT'}) == ('provider_unavailable', 120)
    data['error']['details'].append({'@type': 'google.rpc.QuotaFailure', 'violations': [{'quotaId': 'RequestsPerDay'}]})
    assert policy.classify(429, data, {}) == ('daily_quota', 86400)


def test_persisted_exponential_backoff_and_success_reset(clock):
    session = FakeSession([FakeResponse(429), FakeResponse(503), success()])
    assert call(session) is None
    state = policy.read_state('youtube')
    assert state['last_error'] == 'rate_limit'
    assert state['retry_at'] == clock[0] + 30
    assert call(session) is None
    assert len(session.calls) == 1
    assert policy.read_state('youtube')['used'] == 1
    clock[0] += 30
    assert call(session) is None
    assert policy.read_state('youtube')['retry_at'] == clock[0] + 60
    clock[0] += 60
    assert call(session) == 'ok'
    assert policy.read_state('youtube')['failures'] == 0
    assert policy.read_state('youtube')['used'] == 3


def test_budget_survives_new_session_and_resets_at_taiwan_midnight(clock, monkeypatch):
    monkeypatch.setenv('GEMINI_YOUTUBE_DAILY_REQUESTS', '1')
    assert call(FakeSession([success()])) == 'ok'
    other = FakeSession([success()])
    assert call(other) is None
    assert not other.calls
    clock[0] = datetime(2026, 9, 21, 16, tzinfo=timezone.utc).timestamp()
    assert call(other) == 'ok'
    assert policy.read_state('youtube')['day'] == '2026-09-22'
    assert policy.read_state('youtube')['used'] == 1


def test_scopes_have_independent_budgets(clock, monkeypatch):
    monkeypatch.setenv('GEMINI_YOUTUBE_DAILY_REQUESTS', '0')
    session = FakeSession([success()])
    assert call(session) is None
    assert call(session, scope='live') == 'ok'
    assert policy.read_state('youtube')['used'] == 0
    assert policy.read_state('live')['used'] == 1


def test_key_change_unblocks_without_resetting_count(clock, monkeypatch):
    session = FakeSession([FakeResponse(403), success()])
    assert call(session) is None
    assert call(session) is None
    assert len(session.calls) == 1
    monkeypatch.setattr(gemini, 'GEMINI_API_KEY', 'replacement')
    assert call(session) == 'ok'
    assert policy.read_state('youtube')['used'] == 2
    assert 'replacement' not in policy.state_path('youtube').read_text()


def test_auth_block_survives_midnight_and_manual_revision_recovers(clock, monkeypatch):
    session = FakeSession([FakeResponse(403), success()])
    call(session)
    clock[0] += 86400
    assert call(session) is None
    assert len(session.calls) == 1
    monkeypatch.setenv('GEMINI_POLICY_REVISION', 'account-fixed')
    assert call(session) == 'ok'
    assert policy.read_state('youtube')['used'] == 1


@pytest.mark.parametrize('exception,category', [(asyncio.TimeoutError, 'timeout'), (gemini.aiohttp.ClientConnectionError, 'network')])
def test_network_failures_are_counted_and_deferred(clock, exception, category):
    class BrokenSession:
        def post(self, *args, **kwargs):
            raise exception('sensitive URL must not be logged')
    assert call(BrokenSession()) is None
    state = policy.read_state('youtube')
    assert state['used'] == 1 and state['last_error'] == category
    assert state['retry_at'] == clock[0] + 30


def test_backoff_is_capped_but_provider_delay_is_respected(clock):
    policy.reserve('youtube', 'config', 'request')
    for _ in range(15):
        policy.failed('youtube', 'rate_limit', 'request')
    assert policy.read_state('youtube')['retry_at'] == clock[0] + 3600
    policy.failed('youtube', 'rate_limit', 'request', 7200)
    assert policy.read_state('youtube')['retry_at'] == clock[0] + 7200


def test_bad_request_is_not_repeated_but_other_prompts_still_work(clock):
    session = FakeSession([FakeResponse(400), success()])
    assert call(session) is None
    assert call(session) is None
    assert call(session, prompt='different request') == 'ok'
    assert len(session.calls) == 2


def test_corrupt_or_unwritable_state_fails_closed(clock, monkeypatch):
    path = policy.state_path('youtube')
    path.write_text('{broken')
    session = FakeSession([success()])
    assert call(session) is None
    assert not session.calls
    path.write_text('{}')
    def fail(*args):
        raise policy.PolicyStateError('disk unavailable')
    monkeypatch.setattr(policy, 'write_state', fail)
    assert call(session) is None
    assert not session.calls


def test_concurrent_calls_cannot_overspend(clock, monkeypatch):
    monkeypatch.setenv('GEMINI_YOUTUBE_DAILY_REQUESTS', '1')
    session = FakeSession([success(), success()])
    async def scenario():
        return await asyncio.gather(*(gemini.call_gemini(session, 'hello', usage_scope='youtube') for _ in range(5)))
    results = asyncio.run(scenario())
    assert results.count('ok') == 1
    assert len(session.calls) == 1


def test_cancelled_request_remains_charged(clock):
    class CancelledSession:
        def post(self, *args, **kwargs):
            raise asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        call(CancelledSession())
    assert policy.read_state('youtube')['used'] == 1



def test_request_budget_exhaustion_keeps_youtube_work_pending(clock, monkeypatch, tmp_path):
    import yt_monitor as yt
    from test_yt_monitor import FEED, channel_cfg
    monkeypatch.setattr(yt, 'SEEN_STATE_FILE', tmp_path / 'seen.json')
    monkeypatch.setattr(yt, 'GEMINI_API_KEY', 'test')
    monkeypatch.setattr(yt, 'TELEGRAM_BOT_TOKEN_02', 'test')
    monkeypatch.setattr(yt, 'TELEGRAM_CHAT_ID', 'test')
    monkeypatch.setenv('GEMINI_YOUTUBE_DAILY_REQUESTS', '1')
    state = {'c': ['older']}
    session = FakeSession([FakeResponse(200, FEED), success(), FakeResponse(200)])
    asyncio.run(yt.process_channel(session, channel_cfg(), state))
    record = yt.load_progress()['UC123:newest']
    assert record['summary_completed'] and record['summary_delivered']
    assert not record['research_completed']
    assert len(session.calls) == 3  # RSS, summary, Telegram; research never called.
    next_session = FakeSession([FakeResponse(200, FEED)])
    asyncio.run(yt.process_channel(next_session, channel_cfg(), yt.load_seen_state()))
    assert len(next_session.calls) == 1
    assert policy.read_state('youtube')['used'] == 1

    # The next local budget day resumes only research, using the saved summary.
    clock[0] += 86400
    research_response = FakeResponse(200, json_data={'candidates': [{
        'finishReason': 'STOP', 'content': {'parts': [{'text': 'Checked claim'}]},
        'groundingMetadata': {
            'groundingChunks': [{'web': {'uri': 'https://example.org/source'}}],
            'groundingSupports': [{'segment': {'text': 'Checked claim'}, 'groundingChunkIndices': [0]}],
        },
    }]})
    resumed = FakeSession([FakeResponse(200, FEED), research_response, FakeResponse(200)])
    asyncio.run(yt.process_channel(resumed, channel_cfg(), yt.load_seen_state()))
    assert yt.load_progress()['UC123:newest']['research_delivered']
    assert resumed.calls[1]['json']['tools'] == [{'google_search': {}}]


def test_error_bodies_are_not_logged_or_saved(clock, caplog):
    secret = 'SENSITIVE_PROVIDER_BODY'
    session = FakeSession([FakeResponse(429, json.dumps({'error': {'message': secret}}))])
    call(session)
    assert secret not in caplog.text
    assert secret not in policy.state_path('youtube').read_text()
