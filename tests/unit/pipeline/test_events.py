import asyncio

import pytest

from curbcam.pipeline.events import EventBus, EventEnvelope


@pytest.mark.asyncio
async def test_subscriber_receives_published_event() -> None:
    bus = EventBus()
    sub = bus.subscribe()

    bus.publish(EventEnvelope(kind="event", payload={"speed_kph": 42.0}))

    got = await asyncio.wait_for(sub.get(), timeout=1.0)
    assert got.kind == "event"
    assert got.payload["speed_kph"] == 42.0


@pytest.mark.asyncio
async def test_multiple_subscribers_each_receive_one_copy() -> None:
    bus = EventBus()
    a = bus.subscribe()
    b = bus.subscribe()

    bus.publish(EventEnvelope(kind="event", payload={"speed_kph": 30.0}))

    got_a = await asyncio.wait_for(a.get(), timeout=1.0)
    got_b = await asyncio.wait_for(b.get(), timeout=1.0)
    assert got_a.payload["speed_kph"] == 30.0
    assert got_b.payload["speed_kph"] == 30.0


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery() -> None:
    bus = EventBus()
    sub = bus.subscribe()
    bus.unsubscribe(sub)

    bus.publish(EventEnvelope(kind="event", payload={"x": 1}))

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(sub.get(), timeout=0.1)


@pytest.mark.asyncio
async def test_publish_is_thread_safe_via_loop_call_soon_threadsafe() -> None:
    """The runner thread will call publish_threadsafe() from outside the loop."""
    bus = EventBus()
    bus.bind_loop(asyncio.get_running_loop())
    sub = bus.subscribe()

    import threading

    threading.Thread(
        target=lambda: bus.publish_threadsafe(EventEnvelope(kind="event", payload={}))
    ).start()

    got = await asyncio.wait_for(sub.get(), timeout=1.0)
    assert got.kind == "event"
