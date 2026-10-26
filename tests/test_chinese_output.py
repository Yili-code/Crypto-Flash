import asyncio

import pytest

import tg
from chinese_output import traditional_chinese_message
from fakes import FakeResponse, FakeSession


@pytest.mark.parametrize(("source", "expected"), [
    ("增长降温并未压住通胀，暂停加息的预期仍受物价牵制", "增長降溫並未壓住通脹，暫停加息的預期仍受物價牽制"),
    ("数据发布：前值 3.2%，实际 3.5%，预期 3.4%", "數據發佈：前值 3.2%，實際 3.5%，預期 3.4%"),
    ("BTC ETF inflows +$3.2m · Fed 2026-10-26", "BTC ETF inflows +$3.2m · Fed 2026-10-26"),
    ("臺灣市場與風險", "臺灣市場與風險"),
    ('<a href="https://example.com/新闻?q=经济&amp;x=1">经济新闻</a>',
     '<a href="https://example.com/新闻?q=经济&amp;x=1">經濟新聞</a>'),
    ("链接 https://example.com/新闻?q=经济 经济", "鏈接 https://example.com/新闻?q=经济 經濟"),
    ("&#x7ecf;&#27982; &amp; &lt;市场&gt;", "經濟 &amp; &lt;市場&gt;"),
    ("<pre>数据 = 1</pre><code>经济</code> 数据", "<pre>数据 = 1</pre><code>经济</code> 數據"),
])
def test_visible_prose_is_traditional_without_changing_protected_content(source, expected):
    assert traditional_chinese_message(source) == expected
    assert traditional_chinese_message(expected) == expected


def test_sender_normalizes_both_bots_and_plain_text_retry(monkeypatch):
    async def no_sleep(delay):
        pass
    monkeypatch.setattr(tg.asyncio, "sleep", no_sleep)
    for token in ("token-01", "token-02"):
        session = FakeSession([FakeResponse(400), FakeResponse(200)])
        assert asyncio.run(tg.send_telegram_message(
            session, "test-chat", "<b>市场</b>：预期 3.4%，实际 3.5%", token,
        ))
        assert session.calls[0]["json"]["text"] == "<b>市場</b>：預期 3.4%，實際 3.5%"
        assert session.calls[1]["json"]["text"] == "市場：預期 3.4%，實際 3.5%"
        assert "parse_mode" not in session.calls[1]["json"]
