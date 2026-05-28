"""Raspberry Pi Camera Module via picamera2 (libcamera).

picamera2 is Linux/ARM-only. We import it inside ``open()`` so unit
tests on dev laptops don't need the dependency installed. The CLI's
camera factory raises a clear error if the user picks ``picamera2:N``
on a system without the library.
"""

import time
from typing import Any

import numpy as np


class Picamera2Source:
    def __init__(
        self,
        device_index: int,
        *,
        resolution: tuple[int, int],
        fps_target: float,
    ) -> None:
        self._index = device_index
        self._resolution = resolution
        self._fps_target = fps_target
        self._cam: Any = None

    def open(self) -> None:
        if self._cam is not None:
            return
        try:
            from picamera2 import Picamera2  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError(
                "picamera2 is not installed. On a Raspberry Pi, install with "
                "`uv pip install '.[picamera2]'` (or use the official Docker image)."
            ) from e

        cam = Picamera2(camera_num=self._index)
        config = cam.create_video_configuration(
            main={"size": self._resolution, "format": "BGR888"},
            controls={"FrameRate": self._fps_target},
        )
        cam.configure(config)
        cam.start()
        self._cam = cam

    def read(self) -> tuple[np.ndarray, float] | None:
        if self._cam is None:
            raise RuntimeError("read() before open()")
        frame = self._cam.capture_array("main")
        if frame is None:
            return None
        return frame, time.monotonic()

    def close(self) -> None:
        if self._cam is not None:
            self._cam.stop()
            self._cam.close()
            self._cam = None

    @property
    def resolution(self) -> tuple[int, int]:
        return self._resolution

    @property
    def fps_target(self) -> float:
        return self._fps_target

    @property
    def is_persistent(self) -> bool:
        return True
