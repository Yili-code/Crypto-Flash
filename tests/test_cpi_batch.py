import asyncio
from unittest.mock import AsyncMock

import jin10_monitor as jm
from cpi_batch import merge_release, parse_release


def release(rate="年率", actual="3.5", core="", country="英国", month="9月", identity="20261021140016845800"):
    return {"id": identity, "data": {"content": f"{country}{month}{core}CPI{rate} {actual}%，预期3.4%，前值3.10%。"}}


def test_distinguishes_release_keys_and_ignores_commentary():
    base = parse_release(release())["key"]
    for item in (release(country="美国"), release(month="8月"), release(identity="20261022140016845800")):
        assert parse_release(item)["key"] != base
    assert parse_release(release(core="核心", rate="月率"))["key"] == base
    item = release()
    item["data"]["content"] += " 官员发表讲话。"
    assert parse_release(item) is None
    assert parse_release({"id": "missing-date", "data": release()["data"]}) is None
    item = release()
    item["source"] = "Other"
    assert parse_release(item) is None


def test_four_indicators_render_once_with_values_and_labels():
    items = [release(), release(rate="月率", actual="0.4"),
             release(core="核心", actual="2.8"), release(core="核心", rate="月率", actual="0.2")]
    message = merge_release(items)["_cpi_message"]
    for label in ("整體 CPI 年率（YoY）：3.5%", "整體 CPI 月率（MoM）：0.4%",
                  "核心 CPI 年率（YoY）：2.8%", "核心 CPI 月率（MoM）：0.2%"):
        assert label in message
    assert message.count("預期") == 4
    assert "市場影響" not in message


def test_duplicate_rows_collapse_and_conflicts_remain_visible():
    message = merge_release([release(), release(actual="3.50")])["_cpi_message"]
    assert message.count("預期") == 1
    message = merge_release([release(), release(actual="3.6")])["_cpi_message"]
    assert "來源數值衝突" in message
    assert "3.5%" in message and "3.6%" in message


def test_structured_card_and_text_release_merge_without_duplicate_row():
    card = {"id": "20261021140016000000", "type": 1, "data": {
        "country": "英国", "name": "CPI", "measure": "年率", "time_period": "9月",
        "unit": "%", "actual": "3.50", "consensus": "3.4", "previous": "3.1",
    }}
    assert parse_release(card)["key"] == parse_release(release())["key"]
    assert merge_release([card, release()])["_cpi_message"].count("預期") == 1
    card["data"]["actual"] = None
    assert parse_release(card) is None


def test_different_releases_are_never_merged():
    import pytest
    with pytest.raises(ValueError):
        merge_release([release(), release(country="美国")])


def test_worker_collects_delayed_siblings_without_delaying_other_news(monkeypatch):
    handled = []
    monkeypatch.setattr(jm, "CPI_BATCH_SECONDS", 0.05)

    async def handle(session, item):
        handled.append(item)

    monkeypatch.setattr(jm, "handle_item", handle)

    async def scenario():
        queue = asyncio.Queue()
        worker = asyncio.create_task(jm.outbox_worker(None, queue))
        queue.put_nowait(release())
        queue.put_nowait({"id": "ordinary"})
        await asyncio.sleep(0.01)
        assert handled == [{"id": "ordinary"}]
        queue.put_nowait(release(core="核心", actual="2.8"))
        await asyncio.wait_for(queue.join(), 1)
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())
    assert len(handled) == 2
    assert handled[1]["_cpi_message"].count("預期") == 2


def test_merged_facts_replace_model_prose_and_survive_backlog(monkeypatch):
    item = merge_release([release(), release(core="核心", actual="2.8")])
    monkeypatch.setattr(jm, "GEMINI_API_KEY", "test")
    monkeypatch.setattr(jm, "GEMINI_AVAILABLE", False)
    monkeypatch.setattr(jm, "remember_news", lambda *a, **kw: None)
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(jm, "send_telegram_message", sender)
    monkeypatch.setattr(jm, "summarize_with_gemini", AsyncMock(return_value={
        "tier": "HIGH", "relevant": True, "message": "Incorrect CPI 99%",
    }))
    asyncio.run(jm.handle_item(None, item))
    assert len(jm.backlog.pending()) == 1
    monkeypatch.setattr(jm, "GEMINI_AVAILABLE", True)
    asyncio.run(jm.retry_classification_backlog(None))
    sender.assert_awaited_once()
    assert item["_cpi_message"] in sender.call_args.args[2]
    assert "99%" not in sender.call_args.args[2]
