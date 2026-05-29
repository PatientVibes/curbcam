import pytest

from curbcam.pipeline.events import EventBus, EventEnvelope


@pytest.mark.asyncio
async def test_slow_subscriber_drops_oldest_without_raising() -> None:
    bus = EventBus(maxsize=4)
    q = bus.subscribe()
    # Publish more than maxsize without ever reading.
    for i in range(10):
        bus.publish(EventEnvelope(kind="event", payload={"i": i}))
    # Queue never exceeds maxsize, and publish never raised.
    assert q.qsize() == 4
    # Oldest were dropped — the surviving items are the most recent 4.
    survivors = [q.get_nowait().payload["i"] for _ in range(4)]
    assert survivors == [6, 7, 8, 9]


@pytest.mark.asyncio
async def test_subscribe_default_maxsize_is_bounded() -> None:
    bus = EventBus()
    q = bus.subscribe()
    assert q.maxsize > 0
