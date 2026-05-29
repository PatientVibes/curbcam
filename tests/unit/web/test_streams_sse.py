import asyncio
from types import SimpleNamespace

import pytest

from curbcam.pipeline.events import EventBus, EventEnvelope
from curbcam.web.streams import sse_generator


@pytest.mark.asyncio
async def test_sse_generator_emits_published_event() -> None:
    bus = EventBus()
    sup = SimpleNamespace(bus=bus)
    gen = sse_generator(sup)
    task = asyncio.ensure_future(gen.__anext__())
    await asyncio.sleep(0.05)  # let the generator subscribe and block on get()
    bus.publish(EventEnvelope(kind="event", payload={"id": 7}))
    chunk = await asyncio.wait_for(task, timeout=2.0)
    assert b"event: event" in chunk
    assert b'"id": 7' in chunk
    await gen.aclose()
