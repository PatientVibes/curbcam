"""Generate a directory of JPEGs simulating a vehicle moving L→R or R→L."""

from pathlib import Path

import cv2
import numpy as np


def write_synthetic_run(
    dir_: Path,
    *,
    frames: int = 10,
    step_px: int = 40,
    direction: str = "L2R",
) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    width, height = 640, 480
    start = 100 if direction == "L2R" else width - 140
    sign = 1 if direction == "L2R" else -1
    for i in range(frames):
        img = np.zeros((height, width, 3), dtype=np.uint8)
        x = start + sign * i * step_px
        cv2.rectangle(img, (x, 200), (x + 40, 240), (255, 255, 255), thickness=-1)
        cv2.imwrite(str(dir_ / f"{i:04d}.jpg"), img)
