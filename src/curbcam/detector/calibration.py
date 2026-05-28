"""Calibration data and pixel-to-speed math.

The speed of an object is computed from how far its centroid moved across
frames (pixels), how much wall-clock time elapsed between those frames
(seconds), and the per-direction mm-per-pixel scale stored on the active
Calibration record.

mm_per_s = pixels * mm_per_px
kph     = mm_per_s * (3600 / 1_000_000)
"""

from dataclasses import dataclass

from curbcam.detector.types import TrackedObject

_MM_PER_SEC_TO_KPH = 3600.0 / 1_000_000.0


@dataclass(frozen=True, slots=True)
class Calibration:
    mm_per_px_l2r: float
    mm_per_px_r2l: float


def speed_from_track(track: TrackedObject, cal: Calibration) -> float | None:
    """Return kph for the track, or None if it cannot be computed.

    Returns None when the track has fewer than 2 detections (no displacement)
    or no direction (unknown which calibration to apply).
    """
    if track.direction is None:
        return None
    if len(track.detections) < 2:
        return None

    first = track.detections[0]
    last = track.detections[-1]
    elapsed = last.frame_ts - first.frame_ts
    if elapsed <= 0:
        return None

    dx_px = abs(last.centroid[0] - first.centroid[0])
    mm_per_px = cal.mm_per_px_l2r if track.direction == "L2R" else cal.mm_per_px_r2l
    mm_per_s = (dx_px / elapsed) * mm_per_px
    return mm_per_s * _MM_PER_SEC_TO_KPH
