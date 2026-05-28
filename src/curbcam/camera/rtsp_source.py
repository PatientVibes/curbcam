"""RTSP IP camera via OpenCV with reconnect-on-failure logic.

RTSP streams drop frequently in real-world conditions (network blips,
camera reboots, DHCP changes). This source retries open() up to
``max_open_attempts`` with exponential backoff, and a read() that returns
None signals the pipeline to wait briefly and retry.
"""

import time

import cv2
import numpy as np


class RtspSource:
    def __init__(
        self,
        url: str,
        *,
        resolution: tuple[int, int],
        fps_target: float,
        max_open_attempts: int = 5,
    ) -> None:
        self._url = url
        self._resolution = resolution
        self._fps_target = fps_target
        self._max_open_attempts = max_open_attempts
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> None:
        if self._cap is not None:
            return
        backoff = 0.5
        last_err: Exception | None = None
        for attempt in range(self._max_open_attempts):
            cap = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)
            if cap.isOpened():
                self._cap = cap
                return
            cap.release()
            last_err = RuntimeError(f"RTSP open attempt {attempt + 1} failed")
            time.sleep(backoff)
            backoff = min(backoff * 2, 8.0)
        raise RuntimeError(f"Could not open RTSP {self._url!r}") from last_err

    def read(self) -> tuple[np.ndarray, float] | None:
        if self._cap is None:
            raise RuntimeError("read() before open()")
        ok, frame = self._cap.read()
        if not ok or frame is None:
            # Force reconnect on next read.
            self.close()
            return None
        return frame, time.monotonic()

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    @property
    def resolution(self) -> tuple[int, int]:
        return self._resolution

    @property
    def fps_target(self) -> float:
        return self._fps_target

    @property
    def is_persistent(self) -> bool:
        return True
