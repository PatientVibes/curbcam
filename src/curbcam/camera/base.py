"""The Camera Protocol that every frame source implements."""

from typing import Protocol

import numpy as np


class Camera(Protocol):
    def open(self) -> None: ...

    def read(self) -> tuple[np.ndarray, float] | None:
        """Return (frame_bgr, monotonic_ts) or None on transient failure."""
        ...

    def close(self) -> None: ...

    @property
    def resolution(self) -> tuple[int, int]: ...

    @property
    def fps_target(self) -> float: ...

    @property
    def is_persistent(self) -> bool:
        """True for sources that should be reopened on exhaustion (live cameras).

        False for sources that legitimately end (e.g. a non-looping
        FileReplaySource). Used by PipelineRunner._loop_with_reconnect to
        decide whether to retry or terminate after read() returns None.
        """
        ...
