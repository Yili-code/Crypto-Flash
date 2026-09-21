import asyncio
from html import unescape
from unittest.mock import AsyncMock

import gemini
import yt_monitor as yt
from fakes import FakeResponse, FakeSession
from test_yt_monitor import FEED, channel_cfg


def test_grounded_response_uses_real_source_mapping_and_escapes(monkeypatch):
    monkeypatch.setattr(gemini, 'GEMINI_API_KEY', 'test')
    candidate = {
        'finishReason': 'STOP',
        'content': {'parts': [{'text': 'hidden', 'thought': True}, {'text': 'BTC < 5。'}]},
        'groundingMetadata': {
            'groundingChunks': [{'web': {'uri': 'https://example.org/data', 'title': 'Data & date'}}],
            'groundingSupports': [{'segment': {'text': 'BTC < 5。'}, 'groundingChunkIndices': [0]}],
        },
    }
    session = FakeSession([FakeResponse(200, json_data={'candidates': [candidate]})])
    result = asyncio.run(gemini.call_gemini(session, 'verify', google_search=True))
    assert session.calls[0]['json']['tools'] == [{'google_search': {}}]
    assert 'BTC &lt; 5。 [1]' in result
    assert 'https://example.org/data' in result
    assert 'hidden' not in result


def test_missing_or_unlinked_sources_cannot_count_as_research():
    assert gemini.grounded_text('verified', {}) is None
    assert gemini.grounded_text('verified', {'groundingChunks': [{'web': {'uri': 'https://example.org'}}]}) is None
    assert gemini.grounded_text('claim', {
        'groundingChunks': [{'web': {'uri': 'javascript:bad'}}],
        'groundingSupports': [{'segment': {'text': 'claim'}, 'groundingChunkIndices': [0, 99, -1]}],
    }) is None


def test_truncated_response_is_not_delivered(monkeypatch):
    monkeypatch.setattr(gemini, 'GEMINI_API_KEY', 'test')
    session = FakeSession([FakeResponse(200, json_data={'candidates': [{
        'finishReason': 'MAX_TOKENS', 'content': {'parts': [{'text': 'unfinished'}]},
    }]})])
    assert asyncio.run(gemini.call_gemini(session, 'summarize')) is None


def test_research_failure_preserves_summary_and_discloses_gap(monkeypatch):
    monkeypatch.setattr(yt, 'GEMINI_API_KEY', 'test')
    call = AsyncMock(side_effect=['影片論點 < 3', None])
    monkeypatch.setattr(yt, 'call_gemini', call)
    result = asyncio.run(yt.summarize_video(None, 'https://youtu.be/abc', 'channel focus'))
    assert '影片論點 &lt; 3' in result
    assert '外部查證未完成' in result
    assert call.call_args_list[0].kwargs['system_instruction'] == 'channel focus'
    assert call.call_args_list[1].kwargs['google_search'] is True


def test_video_failure_does_not_research_an_invented_summary(monkeypatch):
    monkeypatch.setattr(yt, 'GEMINI_API_KEY', 'test')
    call = AsyncMock(return_value=None)
    monkeypatch.setattr(yt, 'call_gemini', call)
    assert asyncio.run(yt.summarize_video(None, 'https://youtu.be/abc')) is None
    assert call.await_count == 1


def test_long_report_preserves_all_text_and_fits_telegram():
    text = ('數據 < 5 & 🧠\n' * 900) + 'https://example.org/source'
    from html import escape
    parts = yt.split_message(escape(text, quote=False))
    recovered = ''.join(unescape(part.split('\n', 1)[1]) for part in parts)
    assert recovered == text
    assert all(len(unescape(p).encode('utf-16-le')) // 2 < 4096 for p in parts)


def test_partial_delivery_stays_unread(tmp_path, monkeypatch):
    monkeypatch.setattr(yt, 'SEEN_STATE_FILE', tmp_path / 'seen.json')
    monkeypatch.setattr(yt, 'fetch_feed', AsyncMock(return_value=FEED))
    monkeypatch.setattr(yt, 'summarize_video', AsyncMock(return_value='文' * 8000))
    send = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(yt, 'send_telegram_message', send)
    state = {'c': ['older']}
    asyncio.run(yt.process_channel(None, channel_cfg(), state))
    assert state == {'c': ['older']}
    assert send.await_count == 2
