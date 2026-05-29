"""MJPEG + SSE streaming generators (spec §8.4).

MJPEG: one shared annotated-frame slot, read at a fixed fps regardless of
camera rate. Viewer refcount is incremented on entry and decremented in a
finally so the runner stops encoding when nobody is watching.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import cv2
import numpy as np


def _placeholder_jpeg() -> bytes:
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(
        img,
        "no signal",
        (200, 240),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.2,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    _ok, buf = cv2.imencode(".jpg", img)
    return bytes(buf)


_PLACEHOLDER = _placeholder_jpeg()


async def mjpeg_generator(sup, fps: float = 5.0) -> AsyncIterator[bytes]:  # type: ignore[no-untyped-def]
    sup.add_viewer()
    delay = 1.0 / fps
    try:
        while True:
            frame = sup.latest_annotated() or _PLACEHOLDER
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n"
            )
            await asyncio.sleep(delay)
    finally:
        sup.remove_viewer()


async def sse_generator(sup) -> AsyncIterator[bytes]:  # type: ignore[no-untyped-def]
    q = sup.bus.subscribe()
    try:
        while True:
            try:
                env = await asyncio.wait_for(q.get(), timeout=15.0)
            except TimeoutError:
                yield b": keepalive\n\n"
                continue
            payload = json.dumps(env.payload)
            yield f"event: {env.kind}\ndata: {payload}\n\n".encode()
    finally:
        sup.bus.unsubscribe(q)
