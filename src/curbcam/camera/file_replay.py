"""Replays a directory of JPEG/PNG frames at a target FPS.

Used by:
- developers running curbcam on a laptop without a real camera
- the integration test suite in MVP-2 (Playwright + httpx hit a server
  whose runner is fed by this source).

Files are read in lexical order. If ``loop=True``, when the last frame
is reached the source rewinds to the first.
"""

import logging
import time
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png"})


class FileReplaySource:
    def __init__(self, dir_: Path, *, fps_target: float, loop: bool = False) -> None:
        self._dir = dir_
        self._fps_target = fps_target
        self._loop = loop
        self._files: list[Path] = []
        self._index = 0
        self._opened = False
        self._first_shape: tuple[int, int] | None = None
        self._last_emit: float | None = None

    def open(self) -> None:
        if self._opened:
            return
        self._files = sorted(p for p in self._dir.iterdir() if p.suffix.lower() in _IMAGE_SUFFIXES)
        if not self._files:
            raise FileNotFoundError(f"No image files in {self._dir}")
        # Probe shape from first file.
        first = cv2.imread(str(self._files[0]))
        if first is None:
            raise RuntimeError(f"Could not decode {self._files[0]}")
        h, w = first.shape[:2]
        self._first_shape = (w, h)
        self._opened = True

    def read(self) -> tuple[np.ndarray, float] | None:
        if not self._opened:
            raise RuntimeError("read() before open()")
        attempts = 0
        max_attempts = len(self._files)
        while attempts < max_attempts:
            if self._index >= len(self._files):
                if not self._loop:
                    return None
                self._index = 0
            path = self._files[self._index]
            self._throttle()
            frame = cv2.imread(str(path))
            self._index += 1
            if frame is not None:
                return frame, time.monotonic()
            # Decode failure: log and try the next file in the same call so
            # the pipeline does not mistake it for source exhaustion.
            log.warning("Failed to decode replay frame %s; skipping", path)
            attempts += 1
        return None  # all remaining files were undecodable

    def _throttle(self) -> None:
        if self._fps_target <= 0:
            return
        interval = 1.0 / self._fps_target
        now = time.monotonic()
        if self._last_emit is not None:
            wait = interval - (now - self._last_emit)
            if wait > 0:
                time.sleep(wait)
        self._last_emit = time.monotonic()

    def close(self) -> None:
        self._opened = False
        self._index = 0
        self._last_emit = None

    @property
    def resolution(self) -> tuple[int, int]:
        if self._first_shape is None:
            raise RuntimeError("resolution before open()")
        return self._first_shape

    @property
    def fps_target(self) -> float:
        return self._fps_target

    @property
    def is_persistent(self) -> bool:
        """A looping replay is persistent; a one-shot replay is not."""
        return self._loop
