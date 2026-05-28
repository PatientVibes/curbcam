"""Public dataclasses for the detector module."""

from dataclasses import dataclass, field
from typing import Literal

type Direction = Literal["L2R", "R2L"]


@dataclass(frozen=True, slots=True)
class Detection:
    bbox: tuple[int, int, int, int]  # x, y, w, h in source-image pixels
    centroid: tuple[int, int]
    area_px: int
    frame_ts: float  # monotonic seconds


@dataclass(frozen=True, slots=True)
class TrackedObject:
    id: str  # short uuid, stable across frames
    detections: list[Detection] = field(default_factory=list)
    direction: Direction | None = None
    speed_kph: float | None = None
