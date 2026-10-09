import asyncio

import jin10_monitor as jm


def test_enqueue_drops_the_oldest_item_when_the_outbox_is_full():
    async def scenario():
        outbox = asyncio.Queue(maxsize=2)
        for i in range(4):
            jm.enqueue_item(outbox, {"id": i})
        return [outbox.get_nowait()["id"] for _ in range(outbox.qsize())]

    assert asyncio.run(scenario()) == [2, 3]


def test_enqueue_records_each_overload_drop(monkeypatch):
    drops = []
    monkeypatch.setattr(
        jm.metrics,
        "increment",
        lambda field, amount=1: drops.append((field, amount)) if field == "queue_dropped_total" else None,
    )

    async def scenario():
        outbox = asyncio.Queue(maxsize=1)
        jm.enqueue_item(outbox, {"id": 1})
        jm.enqueue_item(outbox, {"id": 2})

    asyncio.run(scenario())
    assert drops == [("queue_dropped_total", 1)]


def test_enqueue_records_received_item_and_queue_high_water(monkeypatch):
    received = []
    sizes = []
    monkeypatch.setattr(jm.metrics, "observe_received", lambda item: received.append(item["id"]))
    monkeypatch.setattr(jm.metrics, "observe_queue_size", sizes.append)

    async def scenario():
        outbox = asyncio.Queue(maxsize=2)
        jm.enqueue_item(outbox, {"id": 1})
        jm.enqueue_item(outbox, {"id": 2})

    asyncio.run(scenario())
    assert received == [1, 2]
    assert sizes == [1, 2]


def test_enqueue_never_blocks_the_receive_loop():
    # A blocking put here would stall ws.recv() until jin10 drops the connection.
    async def scenario():
        outbox = asyncio.Queue(maxsize=1)
        for i in range(50):
            jm.enqueue_item(outbox, {"id": i})
        return outbox.qsize()

    assert asyncio.run(asyncio.wait_for(scenario(), timeout=5)) == 1


def test_worker_keeps_going_after_an_item_fails(monkeypatch):
    handled = []

    async def flaky_handle_item(session, item):
        handled.append(item["id"])
        if item["id"] == "bad":
            raise RuntimeError("gemini exploded")

    monkeypatch.setattr(jm, "handle_item", flaky_handle_item)

    async def scenario():
        outbox = asyncio.Queue()
        worker = asyncio.create_task(jm.outbox_worker(None, outbox))
        for item_id in ("bad", "good"):
            outbox.put_nowait({"id": item_id})
        await asyncio.wait_for(outbox.join(), timeout=5)
        worker.cancel()

    asyncio.run(scenario())
    assert handled == ["bad", "good"]
