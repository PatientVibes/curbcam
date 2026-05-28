"""In-process pub-sub for finalised events and pipeline status.

Used by MVP-2's SSE endpoint and by future v0.2 webhook/MQTT plugins.
A single fanout point (publish) so adding subscribers is additive.

Threading: publish() must be called from inside the asyncio loop;
publish_threadsafe() may be called from any thread (the detector thread
typically) and bridges into the loop via call_soon_threadsafe.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal

EventKind = Literal["event", "stats", "calibration_changed", "settings_changed"]


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    kind: EventKind
    payload: dict[str, Any] = field(default_factory=dict)


class EventBus:
    def __init__(self) -> None:
        self._subs: list[asyncio.Queue[EventEnvelope]] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue[EventEnvelope]:
        q: asyncio.Queue[EventEnvelope] = asyncio.Queue()
        self._subs.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[EventEnvelope]) -> None:
        try:
            self._subs.remove(q)
        except ValueError:
            pass

    def publish(self, env: EventEnvelope) -> None:
        """Call from inside the asyncio loop."""
        for q in self._subs:
            q.put_nowait(env)

    def publish_threadsafe(self, env: EventEnvelope) -> None:
        """Call from any thread. Requires ``bind_loop`` to have been called."""
        if self._loop is None:
            # No loop bound yet → drop (CLI usage without async server).
            return
        self._loop.call_soon_threadsafe(self.publish, env)
