"""USB camera via OpenCV VideoCapture.

The device path is opened lazily on .open() and closed on .close().
read() returns None on transient failure (caller retries with backoff
in pipeline/runner.py).
"""

import time

import cv2
import numpy as np


class UsbSource:
    def __init__(
        self,
        device: str | int,
        *,
        resolution: tuple[int, int],
        fps_target: float,
    ) -> None:
        self._device = device
        self._resolution = resolution
        self._fps_target = fps_target
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> None:
        if self._cap is not None:
            return
        cap = cv2.VideoCapture(self._device)
        if not cap.isOpened():
            raise RuntimeError(f"Could not open USB camera {self._device!r}")
        w, h = self._resolution
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        cap.set(cv2.CAP_PROP_FPS, self._fps_target)
        self._cap = cap

    def read(self) -> tuple[np.ndarray, float] | None:
        if self._cap is None:
            raise RuntimeError("read() before open()")
        ok, frame = self._cap.read()
        if not ok or frame is None:
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
