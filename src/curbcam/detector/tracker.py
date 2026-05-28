"""Single-object-at-a-time tracker via greedy nearest-centroid matching.

Per-frame: each existing in-flight track tries to claim the closest new
detection within ``max_dist_px``. Unclaimed detections start new tracks.
Tracks not matched on a frame are considered "lost" and immediately
finalised (returned to caller) if they meet ``min_track_frames``;
otherwise they're dropped.

Direction is decided at finalisation time from the sign of
last_centroid.x - first_centroid.x.

This is a deliberately simple tracker: appropriate for the speed-camera
use case where typically 0 or 1 objects are in the frame at once
(a car going past, not a crowd of pedestrians). For multi-object scenes
a Kalman/Hungarian-based tracker would be a future upgrade.
"""

import math
import uuid
from dataclasses import dataclass, field

from curbcam.detector.types import Detection, Direction, TrackedObject


@dataclass
class _LiveTrack:
    id: str
    detections: list[Detection] = field(default_factory=list)

    @property
    def last_centroid(self) -> tuple[int, int]:
        return self.detections[-1].centroid


def _distance(a: tuple[int, int], b: tuple[int, int]) -> float:
    # math.sqrt over ** 0.5 because mypy strict types int ** 0.5 as Any
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return math.sqrt(dx * dx + dy * dy)


def _finalise(track: _LiveTrack) -> TrackedObject:
    first_x = track.detections[0].centroid[0]
    last_x = track.detections[-1].centroid[0]
    direction: Direction = "L2R" if last_x >= first_x else "R2L"
    return TrackedObject(
        id=track.id,
        detections=list(track.detections),
        direction=direction,
        speed_kph=None,  # speed is computed downstream by speed_from_track
    )


class Tracker:
    def __init__(self, max_dist_px: int, min_track_frames: int) -> None:
        self._max_dist = max_dist_px
        self._min_frames = min_track_frames
        self._live: list[_LiveTrack] = []

    def update(self, detections: list[Detection]) -> list[TrackedObject]:
        """Advance state by one frame. Return tracks finalised this frame."""
        unmatched = list(detections)
        survivors: list[_LiveTrack] = []
        finalised: list[TrackedObject] = []

        for track in self._live:
            best_idx = -1
            best_dist = float("inf")
            for i, d in enumerate(unmatched):
                dist = _distance(track.last_centroid, d.centroid)
                if dist < best_dist and dist <= self._max_dist:
                    best_dist = dist
                    best_idx = i
            if best_idx >= 0:
                track.detections.append(unmatched.pop(best_idx))
                survivors.append(track)
            else:
                # Track lost this frame → finalise if long enough.
                if len(track.detections) >= self._min_frames:
                    finalised.append(_finalise(track))
                # else: silently drop (too short to be meaningful)

        # Any detections still unmatched start new tracks.
        for d in unmatched:
            survivors.append(_LiveTrack(id=uuid.uuid4().hex[:8], detections=[d]))

        self._live = survivors
        return finalised

    def flush(self) -> list[TrackedObject]:
        """Finalise all in-flight tracks (used at shutdown)."""
        out = [_finalise(t) for t in self._live if len(t.detections) >= self._min_frames]
        self._live = []
        return out
