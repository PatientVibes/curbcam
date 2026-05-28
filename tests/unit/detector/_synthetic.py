"""Synthetic frame generators for detector tests — no camera needed in CI."""

import numpy as np


def black_frame(width: int = 640, height: int = 480) -> np.ndarray:
    """An all-black BGR frame."""
    return np.zeros((height, width, 3), dtype=np.uint8)


def frame_with_white_rect(
    *,
    width: int = 640,
    height: int = 480,
    x: int,
    y: int,
    w: int,
    h: int,
) -> np.ndarray:
    """Black BGR frame with a single white rectangle at (x, y, w, h)."""
    frame = black_frame(width, height)
    frame[y : y + h, x : x + w] = 255
    return frame
