# curbcam MVP-1 — Headless Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a working headless speed-camera CLI. `curbcam detect --camera file:./fixtures/sample_run --output ./data` reads frames, detects moving objects, calculates speed against an active calibration, and writes events to SQLite + thumbnails to disk. No web UI yet (that's MVP-2).

**Architecture:** Pure-CV `detector/` library over numpy. `camera/` abstraction with `FileReplaySource` as the dev-friendly first implementation (real cameras come later in MVP-1). `config/` Pydantic schema persisted to YAML. `storage/` SQLite via SQLAlchemy + Alembic. `pipeline/runner.py` is the single orchestrator wiring camera → detector → storage. Background-thread for CPU work; an in-process event bus for fanout (used by MVP-2's SSE later).

**Tech Stack:** Python 3.12, uv, OpenCV 4.x (`opencv-python-headless`), NumPy, SQLAlchemy 2.x, Alembic, Pydantic v2 + pydantic-settings, PyYAML, picamera2 (Pi only — lazy-imported), pytest + pytest-asyncio.

**Reference:** Design spec at `docs/specs/2026-05-28-curbcam-design.md` (sections referenced as §N).

---

## Task 1: Project skeleton + uv + pyproject

**Files:**
- Create: `pyproject.toml`
- Create: `src/curbcam/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "curbcam"
version = "0.1.0.dev0"
description = "Modern, neighbor-friendly speed camera for Raspberry Pi"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.12"
dependencies = [
    "numpy>=1.26",
    "opencv-python-headless>=4.10",
    "pydantic>=2.7",
    "pydantic-settings>=2.4",
    "pyyaml>=6.0",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "typer>=0.12",
    "structlog>=24.1",
]

[project.optional-dependencies]
picamera2 = ["picamera2>=0.3.18"]   # Raspberry Pi only
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "ruff>=0.6",
    "mypy>=1.10",
]

[project.scripts]
curbcam = "curbcam.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/curbcam"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-ra --strict-markers --strict-config"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "RUF"]
ignore = ["E501"]   # ruff format handles line length

[tool.mypy]
python_version = "3.12"
strict = true
warn_unreachable = true
```

- [ ] **Step 2: Write `src/curbcam/__init__.py`**

```python
"""curbcam — a modern, neighbor-friendly speed camera."""

__version__ = "0.1.0.dev0"
```

- [ ] **Step 3: Write `tests/__init__.py`**

```python
```

- [ ] **Step 4: Write `tests/conftest.py`**

```python
"""Shared pytest fixtures."""
from __future__ import annotations

import pytest


@pytest.fixture
def fixed_seed() -> int:
    """Stable seed for any test using stochastic helpers."""
    return 42
```

- [ ] **Step 5: Initialise the env and verify pytest runs (zero tests)**

```bash
cd D:/curbcam
uv venv
uv pip install -e ".[dev]"
uv run pytest
```

Expected: `no tests ran in 0.0Xs` exit 0. If `uv` isn't installed, install per https://docs.astral.sh/uv/.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/ tests/
git commit -m "build: project skeleton, uv-managed, pytest configured"
```

---

## Task 2: Detector types

**Files:**
- Create: `src/curbcam/detector/__init__.py`
- Create: `src/curbcam/detector/types.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/unit/detector/__init__.py`
- Create: `tests/unit/detector/test_types.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/detector/test_types.py
import dataclasses

import pytest

from curbcam.detector.types import Detection, TrackedObject


def test_detection_is_frozen() -> None:
    det = Detection(bbox=(10, 20, 30, 40), centroid=(25, 40), area_px=1200, frame_ts=1.5)
    with pytest.raises(dataclasses.FrozenInstanceError):
        det.area_px = 999  # type: ignore[misc]


def test_tracked_object_speed_is_optional() -> None:
    obj = TrackedObject(id="a1b2", detections=[], direction=None, speed_kph=None)
    assert obj.speed_kph is None
    assert obj.direction is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/detector/test_types.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'curbcam.detector'`.

- [ ] **Step 3: Write `src/curbcam/detector/__init__.py`**

```python
"""Pure-CV library: motion detection, tracking, calibration math."""
```

- [ ] **Step 4: Write `src/curbcam/detector/types.py`**

```python
"""Public dataclasses for the detector module."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Direction = Literal["L2R", "R2L"]


@dataclass(frozen=True, slots=True)
class Detection:
    bbox: tuple[int, int, int, int]   # x, y, w, h in source-image pixels
    centroid: tuple[int, int]
    area_px: int
    frame_ts: float                    # monotonic seconds


@dataclass(frozen=True, slots=True)
class TrackedObject:
    id: str                            # short uuid, stable across frames
    detections: list[Detection] = field(default_factory=list)
    direction: Direction | None = None
    speed_kph: float | None = None
```

- [ ] **Step 5: Create test-package `__init__.py` files**

```python
# tests/unit/__init__.py
```

```python
# tests/unit/detector/__init__.py
```

- [ ] **Step 6: Run test to verify it passes**

```bash
uv run pytest tests/unit/detector/test_types.py -v
```

Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add src/curbcam/detector/ tests/unit/
git commit -m "feat(detector): Detection and TrackedObject dataclasses"
```

---

## Task 3: Calibration dataclass + speed math

**Files:**
- Create: `src/curbcam/detector/calibration.py`
- Create: `tests/unit/detector/test_calibration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/detector/test_calibration.py
import pytest

from curbcam.detector.calibration import Calibration, speed_from_track
from curbcam.detector.types import Detection, TrackedObject


def make_track(
    pixels_traveled: int, dt_seconds: float, direction: str
) -> TrackedObject:
    """Two detections, dt seconds apart, centroid shifted by pixels_traveled."""
    return TrackedObject(
        id="t1",
        detections=[
            Detection(bbox=(0, 0, 10, 10), centroid=(100, 100), area_px=100, frame_ts=0.0),
            Detection(
                bbox=(0, 0, 10, 10),
                centroid=(100 + pixels_traveled, 100),
                area_px=100,
                frame_ts=dt_seconds,
            ),
        ],
        direction=direction,
        speed_kph=None,
    )


def test_speed_from_track_l2r_known_calibration() -> None:
    # 100 px in 1 second; calibration says 1 px = 50 mm → 5000 mm/s = 18 kph.
    cal = Calibration(mm_per_px_l2r=50.0, mm_per_px_r2l=50.0)
    track = make_track(pixels_traveled=100, dt_seconds=1.0, direction="L2R")
    assert speed_from_track(track, cal) == pytest.approx(18.0, rel=1e-6)


def test_speed_from_track_r2l_uses_r2l_calibration() -> None:
    # Same px/s but r2l calibration is double → twice the speed.
    cal = Calibration(mm_per_px_l2r=50.0, mm_per_px_r2l=100.0)
    track = make_track(pixels_traveled=100, dt_seconds=1.0, direction="R2L")
    assert speed_from_track(track, cal) == pytest.approx(36.0, rel=1e-6)


def test_speed_from_track_returns_none_when_no_direction() -> None:
    cal = Calibration(mm_per_px_l2r=50.0, mm_per_px_r2l=50.0)
    track = make_track(pixels_traveled=100, dt_seconds=1.0, direction=None)  # type: ignore[arg-type]
    assert speed_from_track(track, cal) is None


def test_speed_from_track_returns_none_when_too_few_detections() -> None:
    cal = Calibration(mm_per_px_l2r=50.0, mm_per_px_r2l=50.0)
    track = TrackedObject(
        id="t1",
        detections=[
            Detection(bbox=(0, 0, 10, 10), centroid=(0, 0), area_px=100, frame_ts=0.0),
        ],
        direction="L2R",
    )
    assert speed_from_track(track, cal) is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/detector/test_calibration.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'curbcam.detector.calibration'`.

- [ ] **Step 3: Write `src/curbcam/detector/calibration.py`**

```python
"""Calibration data and pixel-to-speed math.

The speed of an object is computed from how far its centroid moved across
frames (pixels), how much wall-clock time elapsed between those frames
(seconds), and the per-direction mm-per-pixel scale stored on the active
Calibration record.

mm_per_s = pixels * mm_per_px
kph     = mm_per_s * (3600 / 1_000_000)
"""
from __future__ import annotations

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
    dt = last.frame_ts - first.frame_ts
    if dt <= 0:
        return None

    dx_px = abs(last.centroid[0] - first.centroid[0])
    mm_per_px = cal.mm_per_px_l2r if track.direction == "L2R" else cal.mm_per_px_r2l
    mm_per_s = (dx_px / dt) * mm_per_px
    return mm_per_s * _MM_PER_SEC_TO_KPH
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/detector/test_calibration.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/curbcam/detector/calibration.py tests/unit/detector/test_calibration.py
git commit -m "feat(detector): Calibration dataclass and speed_from_track"
```

---

## Task 4: Motion detection

**Files:**
- Create: `src/curbcam/detector/motion.py`
- Create: `tests/unit/detector/test_motion.py`
- Create: `tests/unit/detector/_synthetic.py` (test helper, not under `src/`)

- [ ] **Step 1: Write the synthetic-frame helper**

```python
# tests/unit/detector/_synthetic.py
"""Synthetic frame generators for detector tests — no camera needed in CI."""
from __future__ import annotations

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
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/detector/test_motion.py
import cv2
import numpy as np

from curbcam.detector.motion import find_motion
from tests.unit.detector._synthetic import frame_with_white_rect


def _to_gray(bgr: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)


def test_find_motion_detects_moved_rectangle() -> None:
    prev = _to_gray(frame_with_white_rect(x=100, y=200, w=40, h=40))
    curr = _to_gray(frame_with_white_rect(x=160, y=200, w=40, h=40))

    detections = find_motion(prev, curr, min_area_px=500, crop=None, frame_ts=1.5)

    # The diff has two blobs (the vacated area and the newly-occupied area).
    # We expect 1 or 2 detections; what matters is that we get a sane bbox
    # whose centroid is within the moving rectangle's union.
    assert len(detections) >= 1
    biggest = max(detections, key=lambda d: d.area_px)
    cx, _ = biggest.centroid
    assert 100 <= cx <= 200, f"centroid x={cx} should be inside the motion zone"


def test_find_motion_returns_empty_when_no_change() -> None:
    prev = _to_gray(frame_with_white_rect(x=100, y=200, w=40, h=40))
    curr = prev.copy()

    detections = find_motion(prev, curr, min_area_px=500, crop=None, frame_ts=1.5)
    assert detections == []


def test_find_motion_respects_min_area_px() -> None:
    # A 4-px-wide rectangle moving 1px → diff blob is tiny.
    prev = _to_gray(frame_with_white_rect(x=100, y=200, w=4, h=4))
    curr = _to_gray(frame_with_white_rect(x=101, y=200, w=4, h=4))

    detections = find_motion(prev, curr, min_area_px=500, crop=None, frame_ts=1.5)
    assert detections == []


def test_find_motion_respects_crop() -> None:
    # Motion happens at x=100, but crop excludes anything below x=300.
    prev = _to_gray(frame_with_white_rect(x=100, y=200, w=40, h=40))
    curr = _to_gray(frame_with_white_rect(x=160, y=200, w=40, h=40))

    crop = (300, 0, 640, 480)   # x_left, y_upper, x_right, y_lower
    detections = find_motion(prev, curr, min_area_px=500, crop=crop, frame_ts=1.5)
    assert detections == []


def test_find_motion_uses_supplied_frame_ts() -> None:
    """frame_ts must reflect capture time, not compute time."""
    prev = _to_gray(frame_with_white_rect(x=100, y=200, w=40, h=40))
    curr = _to_gray(frame_with_white_rect(x=160, y=200, w=40, h=40))

    detections = find_motion(prev, curr, min_area_px=500, crop=None, frame_ts=12345.678)
    assert detections, "expected at least one detection"
    assert all(d.frame_ts == 12345.678 for d in detections)
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run pytest tests/unit/detector/test_motion.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'curbcam.detector.motion'`.

- [ ] **Step 4: Write `src/curbcam/detector/motion.py`**

```python
"""Frame-diff motion detection.

Algorithm: absolute difference between consecutive grayscale frames →
Gaussian blur → binary threshold → dilate → contour extraction. Contours
below ``min_area_px`` are dropped. Optionally clipped to a crop rectangle
in source-image coordinates.

Returned bounding boxes and centroids are always in SOURCE coordinates
(crop is applied internally and translated back).

``frame_ts`` MUST be the capture timestamp of ``curr_gray`` (typically
the monotonic seconds returned by ``camera.read()``). It is propagated
verbatim into every returned Detection so speed calculations downstream
use real elapsed wall-clock between captures, not detector compute time.
"""
from __future__ import annotations

import cv2
import numpy as np

from curbcam.detector.types import Detection


BBox = tuple[int, int, int, int]   # x_left, y_upper, x_right, y_lower


def find_motion(
    prev_gray: np.ndarray,
    curr_gray: np.ndarray,
    *,
    min_area_px: int,
    crop: BBox | None,
    frame_ts: float,
) -> list[Detection]:
    """Return Detections for connected motion blobs above ``min_area_px``."""
    if crop is not None:
        x0, y0, x1, y1 = crop
        prev_view = prev_gray[y0:y1, x0:x1]
        curr_view = curr_gray[y0:y1, x0:x1]
    else:
        x0, y0 = 0, 0
        prev_view = prev_gray
        curr_view = curr_gray

    diff = cv2.absdiff(prev_view, curr_view)
    blurred = cv2.GaussianBlur(diff, (5, 5), 0)
    _, thresh = cv2.threshold(blurred, 25, 255, cv2.THRESH_BINARY)
    dilated = cv2.dilate(thresh, None, iterations=2)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    out: list[Detection] = []
    for c in contours:
        area = int(cv2.contourArea(c))
        if area < min_area_px:
            continue
        x, y, w, h = cv2.boundingRect(c)
        # Translate back to source coordinates.
        src_x, src_y = x + x0, y + y0
        cx, cy = src_x + w // 2, src_y + h // 2
        out.append(
            Detection(
                bbox=(src_x, src_y, w, h),
                centroid=(cx, cy),
                area_px=area,
                frame_ts=frame_ts,
            )
        )
    return out
```

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/unit/detector/test_motion.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/curbcam/detector/motion.py tests/unit/detector/test_motion.py tests/unit/detector/_synthetic.py
git commit -m "feat(detector): find_motion via frame-diff + contour extraction"
```

---

## Task 5: Object tracker

**Files:**
- Create: `src/curbcam/detector/tracker.py`
- Create: `tests/unit/detector/test_tracker.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/detector/test_tracker.py
import pytest

from curbcam.detector.tracker import Tracker
from curbcam.detector.types import Detection


def det(cx: int, ts: float, area: int = 1000) -> Detection:
    """A simple Detection at (cx, 100) with a 20x20 bbox."""
    return Detection(
        bbox=(cx - 10, 90, 20, 20), centroid=(cx, 100), area_px=area, frame_ts=ts
    )


def test_tracker_returns_no_track_when_only_one_detection_seen() -> None:
    t = Tracker(max_dist_px=50, min_track_frames=3)
    completed = t.update([det(100, 0.0)])
    assert completed == []


def test_tracker_finalises_track_after_object_disappears() -> None:
    t = Tracker(max_dist_px=50, min_track_frames=3)
    t.update([det(100, 0.0)])
    t.update([det(120, 0.1)])
    t.update([det(140, 0.2)])
    t.update([det(160, 0.3)])
    completed = t.update([])   # object gone → track finalised

    assert len(completed) == 1
    track = completed[0]
    assert len(track.detections) == 4
    assert track.direction == "L2R"


def test_tracker_detects_r2l_direction() -> None:
    t = Tracker(max_dist_px=50, min_track_frames=3)
    t.update([det(500, 0.0)])
    t.update([det(480, 0.1)])
    t.update([det(460, 0.2)])
    completed = t.update([])
    assert len(completed) == 1
    assert completed[0].direction == "R2L"


def test_tracker_drops_track_below_min_frames() -> None:
    t = Tracker(max_dist_px=50, min_track_frames=3)
    t.update([det(100, 0.0)])
    t.update([det(120, 0.1)])
    # Only 2 frames before disappearance — below min_track_frames.
    completed = t.update([])
    assert completed == []


def test_tracker_starts_new_track_when_object_too_far() -> None:
    t = Tracker(max_dist_px=30, min_track_frames=2)
    t.update([det(100, 0.0)])
    t.update([det(500, 0.1)])     # >30px away → new track started
    completed_after_gap = t.update([])

    # First track had 1 detection (dropped); second track had 1 detection (dropped).
    assert completed_after_gap == []


def test_tracker_assigns_stable_ids() -> None:
    t = Tracker(max_dist_px=50, min_track_frames=2)
    t.update([det(100, 0.0)])
    t.update([det(120, 0.1)])
    completed = t.update([])
    assert len(completed) == 1
    assert len(completed[0].id) >= 4
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/detector/test_tracker.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'curbcam.detector.tracker'`.

- [ ] **Step 3: Write `src/curbcam/detector/tracker.py`**

```python
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
from __future__ import annotations

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
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return (dx * dx + dy * dy) ** 0.5


def _finalise(track: _LiveTrack) -> TrackedObject:
    first_x = track.detections[0].centroid[0]
    last_x = track.detections[-1].centroid[0]
    direction: Direction = "L2R" if last_x >= first_x else "R2L"
    return TrackedObject(
        id=track.id,
        detections=list(track.detections),
        direction=direction,
        speed_kph=None,    # speed is computed downstream by speed_from_track
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
            survivors.append(
                _LiveTrack(id=uuid.uuid4().hex[:8], detections=[d])
            )

        self._live = survivors
        return finalised

    def flush(self) -> list[TrackedObject]:
        """Finalise all in-flight tracks (used at shutdown)."""
        out = [_finalise(t) for t in self._live if len(t.detections) >= self._min_frames]
        self._live = []
        return out
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/detector/test_tracker.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/curbcam/detector/tracker.py tests/unit/detector/test_tracker.py
git commit -m "feat(detector): greedy single-object tracker"
```

---

## Task 6: Config schema + YAML store

**Files:**
- Create: `src/curbcam/config/__init__.py`
- Create: `src/curbcam/config/schema.py`
- Create: `src/curbcam/config/defaults.py`
- Create: `src/curbcam/config/store.py`
- Create: `tests/unit/config/__init__.py`
- Create: `tests/unit/config/test_schema.py`
- Create: `tests/unit/config/test_store.py`

- [ ] **Step 1: Write `src/curbcam/config/__init__.py`**

```python
"""Pydantic-typed configuration model + YAML persistence."""
from curbcam.config.schema import (
    BBox,
    CameraSettings,
    DetectorSettings,
    RetentionSettings,
    ServerSettings,
    Settings,
)
from curbcam.config.store import ConfigStore

__all__ = [
    "BBox",
    "CameraSettings",
    "ConfigStore",
    "DetectorSettings",
    "RetentionSettings",
    "ServerSettings",
    "Settings",
]
```

- [ ] **Step 2: Write the failing schema test**

```python
# tests/unit/config/test_schema.py
import pytest

from curbcam.config.schema import (
    CameraSettings,
    DetectorSettings,
    RetentionSettings,
    ServerSettings,
    Settings,
)


def test_settings_round_trip_via_model_dump() -> None:
    s = Settings()
    dumped = s.model_dump()
    restored = Settings.model_validate(dumped)
    assert restored == s


def test_camera_source_defaults_to_picamera2() -> None:
    s = Settings()
    assert s.camera.source == "picamera2:0"


def test_units_must_be_kph_or_mph() -> None:
    with pytest.raises(ValueError):
        ServerSettings(units="mps")   # type: ignore[arg-type]


def test_detector_crop_is_optional() -> None:
    s = DetectorSettings()
    assert s.crop is None


def test_retention_caps_must_be_positive() -> None:
    with pytest.raises(ValueError):
        RetentionSettings(max_events_per_day=0)
    with pytest.raises(ValueError):
        RetentionSettings(max_total_disk_mb=0)


def test_min_event_speed_must_be_non_negative() -> None:
    with pytest.raises(ValueError):
        ServerSettings(min_event_speed_kph=-1.0)
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run pytest tests/unit/config/test_schema.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'curbcam.config.schema'`.

- [ ] **Step 4: Write `src/curbcam/config/schema.py`**

```python
"""Pydantic models for curbcam settings.

Persisted to YAML on disk. Field labels and help text live in
``defaults.py`` so the settings UI in MVP-2 reads from a single source
of truth.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict


BBox = tuple[int, int, int, int]   # x_left, y_upper, x_right, y_lower


class CameraSettings(BaseModel):
    source: str = "picamera2:0"
    resolution: tuple[PositiveInt, PositiveInt] = (1280, 720)
    fps_target: float = Field(default=15.0, gt=0)


class DetectorSettings(BaseModel):
    min_area_px: PositiveInt = 800
    min_track_frames: PositiveInt = 5
    max_dist_px: PositiveInt = 100
    crop: BBox | None = None


class RetentionSettings(BaseModel):
    max_events_per_day: PositiveInt = 500
    max_total_disk_mb: PositiveInt = 5000


class ServerSettings(BaseModel):
    units: Literal["kph", "mph"] = "kph"
    min_event_speed_kph: float = Field(default=5.0, ge=0)
    log_level: Literal["DEBUG", "INFO", "WARNING"] = "INFO"


class Settings(BaseSettings):
    """Root settings model. Env vars override fields, e.g.
    ``CURBCAM_CAMERA__SOURCE=rtsp://...`` overrides ``camera.source``.
    """

    model_config = SettingsConfigDict(
        env_prefix="CURBCAM_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    camera: CameraSettings = CameraSettings()
    detector: DetectorSettings = DetectorSettings()
    retention: RetentionSettings = RetentionSettings()
    server: ServerSettings = ServerSettings()
```

- [ ] **Step 5: Run schema test to verify it passes**

```bash
uv run pytest tests/unit/config/test_schema.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Write the store test**

```python
# tests/unit/config/test_store.py
from pathlib import Path

import pytest

from curbcam.config.schema import Settings
from curbcam.config.store import ConfigStore


def test_load_creates_file_with_defaults_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "curbcam.yaml"
    store = ConfigStore(path)
    s = store.load()
    assert isinstance(s, Settings)
    assert path.exists()


def test_save_then_load_round_trips_values(tmp_path: Path) -> None:
    path = tmp_path / "curbcam.yaml"
    store = ConfigStore(path)
    s = store.load()
    s = s.model_copy(update={
        "server": s.server.model_copy(update={"units": "mph", "min_event_speed_kph": 10.0}),
    })
    store.save(s)

    reloaded = ConfigStore(path).load()
    assert reloaded.server.units == "mph"
    assert reloaded.server.min_event_speed_kph == 10.0


def test_env_var_overrides_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CURBCAM_CAMERA__SOURCE", "rtsp://override-host/stream")
    path = tmp_path / "curbcam.yaml"
    store = ConfigStore(path)
    s = store.load()
    assert s.camera.source == "rtsp://override-host/stream"
```

Note: there is no "env values don't leak into the YAML on save" guarantee in
MVP-1 — if you call `store.save(settings)` while an env var is overriding a
field, the env value is what gets persisted. The MVP-2 settings PUT route
will receive only user-typed form values and avoid this entirely. The
README documents the recommendation: set the env var and don't save
settings while it's set.

- [ ] **Step 7: Run store test to verify it fails**

```bash
uv run pytest tests/unit/config/test_store.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'curbcam.config.store'`.

- [ ] **Step 8: Write `src/curbcam/config/defaults.py`**

```python
"""Single source of truth for field labels and help text.

Consumed by the MVP-2 settings UI to render labels/tooltips. Keys are the
dotted path used by ``Settings`` (e.g. ``"camera.source"``). Whenever a
field is added to ``schema.py``, add a row here too — the test suite in
MVP-2 will assert every field has a label.
"""
from __future__ import annotations

FIELD_LABELS: dict[str, tuple[str, str]] = {
    # key: (label, help)
    "camera.source":               ("Camera source",       "picamera2:0 | usb:/dev/video0 | rtsp://... | file:./path"),
    "camera.resolution":           ("Resolution",          "Width x height in pixels"),
    "camera.fps_target":           ("Target frame rate",   "Frames per second the camera should try to deliver"),
    "detector.min_area_px":        ("Min motion area",     "Ignore moving objects smaller than this (pixels)"),
    "detector.min_track_frames":   ("Min track frames",    "An object must be seen this many frames to count as an event"),
    "detector.max_dist_px":        ("Tracker step",        "Maximum per-frame centroid movement that still counts as the same object"),
    "detector.crop":               ("Detection region",    "Rectangle within the frame where motion is checked (set by alignment wizard)"),
    "retention.max_events_per_day":("Max events / day",    "Cap on how many events to keep per day before pruning"),
    "retention.max_total_disk_mb": ("Max total disk (MB)", "Total size of media/ before old events are pruned"),
    "server.units":                ("Display units",       "kph or mph for everything user-facing"),
    "server.min_event_speed_kph":  ("Min event speed",     "Events slower than this are dropped before storage"),
    "server.log_level":            ("Log level",           "DEBUG / INFO / WARNING"),
}
```

- [ ] **Step 9: Write `src/curbcam/config/store.py`**

```python
"""Load and save Settings as YAML.

Behaviour:
- ``load()`` reads the YAML if present (creates with defaults if not),
  then constructs ``Settings``. Pydantic-settings overlays env vars on
  top of the YAML at construction time, so the returned instance is
  YAML ⊕ env.
- ``save(s)`` writes the in-memory values to YAML as-is. If an env var
  was overriding a field at save time, that env value is what gets
  persisted — MVP-1 does not try to be clever about this. MVP-2's
  settings UI will accept user-typed form values and call save() with
  those, sidestepping the problem.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from curbcam.config.schema import Settings


class ConfigStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Settings:
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            default = Settings()
            self._write_yaml(default.model_dump(mode="json"))
            return default

        with self._path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return Settings.model_validate(data)

    def save(self, settings: Settings) -> None:
        self._write_yaml(settings.model_dump(mode="json"))

    def _write_yaml(self, data: dict) -> None:
        with self._path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, indent=2)
```

- [ ] **Step 10: Create `tests/unit/config/__init__.py`**

```python
# tests/unit/config/__init__.py
```

- [ ] **Step 11: Run all config tests**

```bash
uv run pytest tests/unit/config/ -v
```

Expected: 9 passed.

- [ ] **Step 12: Commit**

```bash
git add src/curbcam/config/ tests/unit/config/
git commit -m "feat(config): Pydantic schema, defaults catalog, YAML store with env-var overrides"
```

---

## Task 7: Storage models + Alembic init

**Files:**
- Create: `src/curbcam/storage/__init__.py`
- Create: `src/curbcam/storage/models.py`
- Create: `src/curbcam/storage/db.py`
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/script.py.mako`
- Create: `migrations/versions/.gitkeep`
- Create: `tests/unit/storage/__init__.py`
- Create: `tests/unit/storage/test_db.py`

- [ ] **Step 1: Write `src/curbcam/storage/__init__.py`**

```python
"""SQLite + SQLAlchemy + Alembic-managed schema and media-file management."""
from curbcam.storage.db import Database
from curbcam.storage.models import Base, Calibration, Event

__all__ = ["Base", "Calibration", "Database", "Event"]
```

- [ ] **Step 2: Write `src/curbcam/storage/models.py`**

```python
"""SQLAlchemy ORM models for events and calibrations.

Direct map of the schema in design spec §7.1.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Calibration(Base):
    __tablename__ = "calibrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_utc: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    mm_per_px_l2r: Mapped[float] = mapped_column(Numeric, nullable=False)
    mm_per_px_r2l: Mapped[float] = mapped_column(Numeric, nullable=False)
    reference_distance_mm: Mapped[float] = mapped_column(Numeric, nullable=False)
    reference_points_json: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    events: Mapped[list[Event]] = relationship(back_populates="calibration")

    __table_args__ = (
        Index(
            "one_active_calibration",
            "active",
            unique=True,
            sqlite_where="active = 1",
        ),
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts_utc: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    speed_kph: Mapped[float] = mapped_column(Numeric, nullable=False)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    frame_count: Mapped[int] = mapped_column(Integer, nullable=False)
    track_len_px: Mapped[int] = mapped_column(Integer, nullable=False)
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    thumb_path: Mapped[str] = mapped_column(Text, nullable=False)
    calibration_id: Mapped[int | None] = mapped_column(
        ForeignKey("calibrations.id"), nullable=True
    )

    calibration: Mapped[Calibration | None] = relationship(back_populates="events")

    __table_args__ = (Index("events_ts", "ts_utc"),)
```

- [ ] **Step 3: Write `src/curbcam/storage/db.py`**

```python
"""Thin wrapper around SQLAlchemy engine + session factory.

Enables SQLite WAL journaling at first connection so the writer (detector
thread) and readers (web server, in MVP-2) never block each other.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


class Database:
    def __init__(self, url: str) -> None:
        self._engine: Engine = create_engine(url, future=True)
        _enable_sqlite_wal(self._engine)
        self._sessionmaker = sessionmaker(bind=self._engine, expire_on_commit=False)

    @classmethod
    def for_sqlite_path(cls, path: Path) -> Database:
        path.parent.mkdir(parents=True, exist_ok=True)
        return cls(f"sqlite:///{path}")

    @property
    def engine(self) -> Engine:
        return self._engine

    def session(self) -> Session:
        return self._sessionmaker()


def _enable_sqlite_wal(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()
```

- [ ] **Step 4: Write `alembic.ini`**

```ini
[alembic]
script_location = migrations
prepend_sys_path = .
version_path_separator = os
sqlalchemy.url = sqlite:///data/curbcam.sqlite

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 5: Write `migrations/env.py`**

```python
"""Alembic env script — uses curbcam's Base for autogeneration."""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from curbcam.storage.models import Base


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,   # SQLite needs batch for ALTER
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 6: Write `migrations/script.py.mako`**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 7: Create empty `migrations/versions/.gitkeep`**

```
```

- [ ] **Step 8: Generate the initial migration**

```bash
cd D:/curbcam
mkdir -p data
uv run alembic revision --autogenerate -m "initial schema: events + calibrations"
```

Expected: one new file under `migrations/versions/<rev>_initial_schema_events_calibrations.py` with `op.create_table(...)` for both tables.

- [ ] **Step 9: Run the migration against a throwaway DB to verify it executes**

```bash
rm -f data/curbcam.sqlite
uv run alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade  -> <rev>, initial schema: events + calibrations`. No errors.

- [ ] **Step 10: Write the failing db test**

```python
# tests/unit/storage/test_db.py
from pathlib import Path

from curbcam.storage import Calibration, Database, Event
from curbcam.storage.models import Base
import datetime as dt


def test_database_creates_tables_and_round_trips_an_event(tmp_path: Path) -> None:
    db = Database.for_sqlite_path(tmp_path / "test.sqlite")
    Base.metadata.create_all(db.engine)

    with db.session() as s:
        cal = Calibration(
            created_utc=dt.datetime(2026, 5, 28, 12, 0, 0),
            mm_per_px_l2r=41.3,
            mm_per_px_r2l=41.5,
            reference_distance_mm=4700.0,
            reference_points_json='{"a": [10, 20], "b": [247, 22]}',
            active=True,
            notes=None,
        )
        s.add(cal)
        s.flush()
        event = Event(
            ts_utc=dt.datetime(2026, 5, 28, 12, 0, 5),
            speed_kph=42.7,
            direction="L2R",
            frame_count=12,
            track_len_px=237,
            image_path="events/2026/05/28/event_1.jpg",
            thumb_path="thumbs/2026/05/28/event_1.jpg",
            calibration_id=cal.id,
        )
        s.add(event)
        s.commit()

    with db.session() as s:
        events = s.query(Event).all()
        assert len(events) == 1
        assert events[0].speed_kph == 42.7


def test_wal_journaling_is_enabled(tmp_path: Path) -> None:
    db = Database.for_sqlite_path(tmp_path / "wal.sqlite")
    with db.engine.connect() as conn:
        mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
        assert mode == "wal"


def test_wal_journaling_persists_across_connections(tmp_path: Path) -> None:
    """A fresh Database wrapper on the same file must still see WAL active."""
    path = tmp_path / "wal-persist.sqlite"
    Database.for_sqlite_path(path)   # first connect sets PRAGMA
    db = Database.for_sqlite_path(path)
    with db.engine.connect() as conn:
        mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
        assert mode == "wal"


def test_unique_active_calibration_constraint_enforced_at_db_layer(
    tmp_path: Path,
) -> None:
    """Defense in depth: even bypassing the repo, the partial unique index fires."""
    import datetime as dt
    import sqlalchemy.exc as sa_exc

    db = Database.for_sqlite_path(tmp_path / "constraint.sqlite")
    Base.metadata.create_all(db.engine)
    with db.session() as s:
        s.add(Calibration(
            created_utc=dt.datetime(2026, 5, 28, 12, 0, 0),
            mm_per_px_l2r=40.0, mm_per_px_r2l=40.0,
            reference_distance_mm=4000.0, reference_points_json="[]",
            active=True, notes=None,
        ))
        s.commit()
    with db.session() as s:
        s.add(Calibration(
            created_utc=dt.datetime(2026, 5, 28, 12, 1, 0),
            mm_per_px_l2r=41.0, mm_per_px_r2l=41.0,
            reference_distance_mm=4100.0, reference_points_json="[]",
            active=True, notes=None,
        ))
        with pytest.raises(sa_exc.IntegrityError):
            s.commit()


# Imports for the test above — kept here to keep the simple test above untouched.
import pytest  # noqa: E402
```

- [ ] **Step 11: Create `tests/unit/storage/__init__.py` and run tests**

```python
# tests/unit/storage/__init__.py
```

```bash
uv run pytest tests/unit/storage/ -v
```

Expected: 4 passed.

- [ ] **Step 12: Commit**

```bash
git add src/curbcam/storage/ alembic.ini migrations/ tests/unit/storage/
git commit -m "feat(storage): SQLAlchemy models + WAL-enabled engine + Alembic initial migration"
```

---

## Task 8: Storage helpers — calibration + event repositories

**Files:**
- Create: `src/curbcam/storage/repositories.py`
- Create: `tests/unit/storage/test_repositories.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/storage/test_repositories.py
import datetime as dt
from pathlib import Path

import pytest

from curbcam.storage import Calibration, Database, Event
from curbcam.storage.models import Base
from curbcam.storage.repositories import CalibrationRepo, EventRepo


@pytest.fixture
def db(tmp_path: Path) -> Database:
    d = Database.for_sqlite_path(tmp_path / "repo.sqlite")
    Base.metadata.create_all(d.engine)
    return d


def test_calibration_repo_save_new_marks_only_one_active(db: Database) -> None:
    repo = CalibrationRepo(db)
    repo.save_new_active(
        mm_per_px_l2r=40.0,
        mm_per_px_r2l=40.0,
        reference_distance_mm=4000.0,
        reference_points_json="[]",
    )
    repo.save_new_active(
        mm_per_px_l2r=42.0,
        mm_per_px_r2l=42.0,
        reference_distance_mm=4200.0,
        reference_points_json="[]",
    )
    active = repo.get_active()
    assert active is not None
    assert active.mm_per_px_l2r == 42.0

    with db.session() as s:
        actives = s.query(Calibration).filter(Calibration.active.is_(True)).all()
        assert len(actives) == 1


def test_calibration_repo_get_active_returns_none_when_empty(db: Database) -> None:
    repo = CalibrationRepo(db)
    assert repo.get_active() is None


def test_event_repo_save_and_list_recent(db: Database) -> None:
    cal_repo = CalibrationRepo(db)
    cal_repo.save_new_active(40.0, 40.0, 4000.0, "[]")
    cal = cal_repo.get_active()
    assert cal is not None

    repo = EventRepo(db)
    for i in range(3):
        repo.save(
            ts_utc=dt.datetime(2026, 5, 28, 12, i, 0),
            speed_kph=30.0 + i,
            direction="L2R",
            frame_count=10,
            track_len_px=200,
            image_path=f"events/x_{i}.jpg",
            thumb_path=f"thumbs/x_{i}.jpg",
            calibration_id=cal.id,
        )

    recent = repo.list_recent(limit=2)
    assert len(recent) == 2
    # Newest first by ts_utc DESC.
    assert recent[0].speed_kph == 32.0
    assert recent[1].speed_kph == 31.0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/storage/test_repositories.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'curbcam.storage.repositories'`.

- [ ] **Step 3: Write `src/curbcam/storage/repositories.py`**

```python
"""Thin repository wrappers over the ORM.

Why: keep callers (the pipeline runner, the API routes) free from
SQLAlchemy session boilerplate, and make the active-calibration
invariant a single function call.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import update

from curbcam.storage.db import Database
from curbcam.storage.models import Calibration, Event


class CalibrationRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def save_new_active(
        self,
        mm_per_px_l2r: float,
        mm_per_px_r2l: float,
        reference_distance_mm: float,
        reference_points_json: str,
        notes: str | None = None,
    ) -> Calibration:
        """Insert a new calibration row and mark it as the only active one."""
        with self._db.session() as s:
            # Deactivate any currently-active row(s).
            s.execute(update(Calibration).where(Calibration.active.is_(True)).values(active=False))
            cal = Calibration(
                created_utc=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
                mm_per_px_l2r=mm_per_px_l2r,
                mm_per_px_r2l=mm_per_px_r2l,
                reference_distance_mm=reference_distance_mm,
                reference_points_json=reference_points_json,
                active=True,
                notes=notes,
            )
            s.add(cal)
            s.commit()
            s.refresh(cal)
            return cal

    def get_active(self) -> Calibration | None:
        with self._db.session() as s:
            return s.query(Calibration).filter(Calibration.active.is_(True)).one_or_none()


class EventRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def save(
        self,
        *,
        ts_utc: dt.datetime,
        speed_kph: float,
        direction: str,
        frame_count: int,
        track_len_px: int,
        image_path: str,
        thumb_path: str,
        calibration_id: int | None,
    ) -> Event:
        with self._db.session() as s:
            event = Event(
                ts_utc=ts_utc,
                speed_kph=speed_kph,
                direction=direction,
                frame_count=frame_count,
                track_len_px=track_len_px,
                image_path=image_path,
                thumb_path=thumb_path,
                calibration_id=calibration_id,
            )
            s.add(event)
            s.commit()
            s.refresh(event)
            return event

    def list_recent(self, limit: int = 20) -> list[Event]:
        with self._db.session() as s:
            return (
                s.query(Event)
                .order_by(Event.ts_utc.desc())
                .limit(limit)
                .all()
            )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/storage/test_repositories.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/curbcam/storage/repositories.py tests/unit/storage/test_repositories.py
git commit -m "feat(storage): CalibrationRepo + EventRepo with single-active invariant"
```

---

## Task 9: Media writer (event JPEGs + thumbnails)

**Files:**
- Create: `src/curbcam/storage/media.py`
- Create: `tests/unit/storage/test_media.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/storage/test_media.py
import datetime as dt
from pathlib import Path

import cv2
import numpy as np

from curbcam.storage.media import MediaWriter


def test_save_event_image_writes_full_and_thumb(tmp_path: Path) -> None:
    writer = MediaWriter(media_root=tmp_path)
    frame = np.full((480, 640, 3), fill_value=128, dtype=np.uint8)
    ts = dt.datetime(2026, 5, 28, 14, 30, 5)

    full_rel, thumb_rel = writer.save_event_image(
        frame=frame, event_id=42, ts_utc=ts, speed_kph=37.5, direction="L2R"
    )

    full_abs = tmp_path / full_rel
    thumb_abs = tmp_path / thumb_rel
    assert full_abs.exists()
    assert thumb_abs.exists()
    assert full_rel == "events/2026/05/28/event_42.jpg"
    assert thumb_rel == "thumbs/2026/05/28/event_42.jpg"

    full = cv2.imread(str(full_abs))
    thumb = cv2.imread(str(thumb_abs))
    assert full.shape == (480, 640, 3)
    assert thumb.shape[1] == 320   # default thumb width
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/storage/test_media.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'curbcam.storage.media'`.

- [ ] **Step 3: Write `src/curbcam/storage/media.py`**

```python
"""Write event images and thumbnails to the media root.

Layout (matches design spec §7.2):
    media/events/YYYY/MM/DD/event_<id>.jpg
    media/thumbs/YYYY/MM/DD/event_<id>.jpg

Annotation: the full image and thumbnail both get a small bottom-strip
overlay with timestamp + speed + direction arrow. Bounding boxes etc.
are NOT persisted (see design spec §7.2).
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import cv2
import numpy as np

_THUMB_WIDTH = 320
_JPEG_QUALITY = 85


class MediaWriter:
    def __init__(self, media_root: Path) -> None:
        self._root = media_root

    def save_event_image(
        self,
        *,
        frame: np.ndarray,
        event_id: int,
        ts_utc: dt.datetime,
        speed_kph: float,
        direction: str,
    ) -> tuple[str, str]:
        """Write full + thumb, return their paths RELATIVE to the media root."""
        date_suffix = ts_utc.strftime("%Y/%m/%d")
        rel_full = f"events/{date_suffix}/event_{event_id}.jpg"
        rel_thumb = f"thumbs/{date_suffix}/event_{event_id}.jpg"

        annotated = _annotate(frame, ts_utc=ts_utc, speed_kph=speed_kph, direction=direction)

        full_abs = self._root / rel_full
        thumb_abs = self._root / rel_thumb
        full_abs.parent.mkdir(parents=True, exist_ok=True)
        thumb_abs.parent.mkdir(parents=True, exist_ok=True)

        cv2.imwrite(str(full_abs), annotated, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY])

        h, w = annotated.shape[:2]
        thumb_h = int(h * (_THUMB_WIDTH / w))
        thumb = cv2.resize(annotated, (_THUMB_WIDTH, thumb_h), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(thumb_abs), thumb, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY])

        return rel_full, rel_thumb


def _annotate(
    frame: np.ndarray,
    *,
    ts_utc: dt.datetime,
    speed_kph: float,
    direction: str,
) -> np.ndarray:
    out = frame.copy()
    h, w = out.shape[:2]
    strip_h = 30
    # Dark strip across the bottom for legibility.
    cv2.rectangle(out, (0, h - strip_h), (w, h), (0, 0, 0), thickness=-1)
    # ASCII direction marker: cv2.putText with the default Hershey font
    # cannot render Unicode arrows (renders as "?"). ">>" and "<<" are
    # visually clear and font-safe everywhere OpenCV runs.
    arrow = ">>" if direction == "L2R" else "<<"
    text = f"{ts_utc.strftime('%Y-%m-%d %H:%M:%S')}  {speed_kph:5.1f} kph  {arrow}"
    cv2.putText(
        out,
        text,
        (8, h - 8),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return out
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/storage/test_media.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/curbcam/storage/media.py tests/unit/storage/test_media.py
git commit -m "feat(storage): MediaWriter with bottom-strip annotation + thumbnails"
```

---

## Task 10: Camera abstraction + FileReplaySource

**Files:**
- Create: `src/curbcam/camera/__init__.py`
- Create: `src/curbcam/camera/base.py`
- Create: `src/curbcam/camera/file_replay.py`
- Create: `tests/unit/camera/__init__.py`
- Create: `tests/unit/camera/test_file_replay.py`

- [ ] **Step 1: Write `src/curbcam/camera/__init__.py`**

```python
"""Frame-source abstraction. Detector never depends on this directly."""
from curbcam.camera.base import Camera
from curbcam.camera.file_replay import FileReplaySource

__all__ = ["Camera", "FileReplaySource"]
```

- [ ] **Step 2: Write `src/curbcam/camera/base.py`**

```python
"""The Camera Protocol that every frame source implements."""
from __future__ import annotations

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
```

- [ ] **Step 3: Write the failing test**

```python
# tests/unit/camera/test_file_replay.py
from pathlib import Path

import cv2
import numpy as np

from curbcam.camera.file_replay import FileReplaySource


def _write_jpgs(dir_: Path, count: int) -> None:
    for i in range(count):
        img = np.full((120, 160, 3), fill_value=10 + i, dtype=np.uint8)
        cv2.imwrite(str(dir_ / f"{i:04d}.jpg"), img)


def test_file_replay_reads_frames_in_order(tmp_path: Path) -> None:
    _write_jpgs(tmp_path, count=3)
    cam = FileReplaySource(tmp_path, fps_target=30.0)
    cam.open()
    try:
        frames = []
        while (got := cam.read()) is not None:
            frames.append(got)
        assert len(frames) == 3
        # Pixel values increase by 1 per frame, so means do too.
        means = [float(f[0].mean()) for f in frames]
        assert means[0] < means[1] < means[2]
    finally:
        cam.close()


def test_file_replay_resolution_matches_first_frame(tmp_path: Path) -> None:
    _write_jpgs(tmp_path, count=1)
    cam = FileReplaySource(tmp_path, fps_target=30.0)
    cam.open()
    try:
        assert cam.resolution == (160, 120)
    finally:
        cam.close()


def test_file_replay_loops_when_loop_true(tmp_path: Path) -> None:
    _write_jpgs(tmp_path, count=2)
    cam = FileReplaySource(tmp_path, fps_target=30.0, loop=True)
    cam.open()
    try:
        got = [cam.read() for _ in range(5)]
        assert all(f is not None for f in got)
    finally:
        cam.close()
```

- [ ] **Step 4: Run test to verify it fails**

```bash
uv run pytest tests/unit/camera/test_file_replay.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'curbcam.camera.file_replay'`.

- [ ] **Step 5: Write `src/curbcam/camera/file_replay.py`**

```python
"""Replays a directory of JPEG/PNG frames at a target FPS.

Used by:
- developers running curbcam on a laptop without a real camera
- the integration test suite in MVP-2 (Playwright + httpx hit a server
  whose runner is fed by this source).

Files are read in lexical order. If ``loop=True``, when the last frame
is reached the source rewinds to the first.
"""
from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

_IMAGE_GLOBS = ("*.jpg", "*.jpeg", "*.png")


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
        files: list[Path] = []
        for pattern in _IMAGE_GLOBS:
            files.extend(self._dir.glob(pattern))
        self._files = sorted(files)
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
        if self._index >= len(self._files):
            if not self._loop:
                return None
            self._index = 0
        # Throttle to fps_target.
        self._throttle()
        frame = cv2.imread(str(self._files[self._index]))
        self._index += 1
        if frame is None:
            return None
        return frame, time.monotonic()

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
```

- [ ] **Step 6: Run test to verify it passes**

```bash
uv run pytest tests/unit/camera/test_file_replay.py -v
```

Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add src/curbcam/camera/__init__.py src/curbcam/camera/base.py src/curbcam/camera/file_replay.py tests/unit/camera/
git commit -m "feat(camera): Camera Protocol + FileReplaySource for dev/test"
```

---

## Task 11: USB + RTSP camera sources

**Files:**
- Create: `src/curbcam/camera/usb_source.py`
- Create: `src/curbcam/camera/rtsp_source.py`
- Create: `tests/unit/camera/test_usb_source.py` (skip-if-no-hw)
- Create: `tests/unit/camera/test_rtsp_source.py` (skip-if-no-net)

- [ ] **Step 1: Write `src/curbcam/camera/usb_source.py`**

```python
"""USB camera via OpenCV VideoCapture.

The device path is opened lazily on .open() and closed on .close().
read() returns None on transient failure (caller retries with backoff
in pipeline/runner.py).
"""
from __future__ import annotations

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
```

- [ ] **Step 2: Write `src/curbcam/camera/rtsp_source.py`**

```python
"""RTSP IP camera via OpenCV with reconnect-on-failure logic.

RTSP streams drop frequently in real-world conditions (network blips,
camera reboots, DHCP changes). This source retries open() up to
``max_open_attempts`` with exponential backoff, and a read() that returns
None signals the pipeline to wait briefly and retry.
"""
from __future__ import annotations

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
```

- [ ] **Step 3: Write a no-hardware sanity test for USB**

```python
# tests/unit/camera/test_usb_source.py
"""USB source tests — skipped unless a real device is available.

Set CURBCAM_TEST_USB_DEVICE=/dev/video0 (or an integer) to enable.
"""
import os

import pytest

from curbcam.camera.usb_source import UsbSource


_DEVICE = os.environ.get("CURBCAM_TEST_USB_DEVICE")


@pytest.mark.skipif(_DEVICE is None, reason="set CURBCAM_TEST_USB_DEVICE to run")
def test_usb_source_reads_a_frame() -> None:
    device: str | int = int(_DEVICE) if _DEVICE.isdigit() else _DEVICE   # type: ignore[arg-type, union-attr]
    cam = UsbSource(device, resolution=(640, 480), fps_target=15.0)
    cam.open()
    try:
        got = cam.read()
        assert got is not None
        frame, _ts = got
        assert frame.shape[2] == 3
    finally:
        cam.close()


def test_usb_source_read_before_open_raises() -> None:
    cam = UsbSource(0, resolution=(640, 480), fps_target=15.0)
    with pytest.raises(RuntimeError):
        cam.read()
```

- [ ] **Step 4: Write a no-network sanity test for RTSP**

```python
# tests/unit/camera/test_rtsp_source.py
"""RTSP source tests — skipped unless a real URL is available.

Set CURBCAM_TEST_RTSP_URL=rtsp://... to enable.
"""
import os

import pytest

from curbcam.camera.rtsp_source import RtspSource


_URL = os.environ.get("CURBCAM_TEST_RTSP_URL")


@pytest.mark.skipif(_URL is None, reason="set CURBCAM_TEST_RTSP_URL to run")
def test_rtsp_source_reads_a_frame() -> None:
    cam = RtspSource(_URL or "", resolution=(640, 480), fps_target=15.0)  # noqa: SIM222
    cam.open()
    try:
        got = cam.read()
        assert got is not None
    finally:
        cam.close()


def test_rtsp_source_read_before_open_raises() -> None:
    cam = RtspSource("rtsp://noop", resolution=(640, 480), fps_target=15.0)
    with pytest.raises(RuntimeError):
        cam.read()
```

- [ ] **Step 5: Run the no-hardware tests**

```bash
uv run pytest tests/unit/camera/test_usb_source.py tests/unit/camera/test_rtsp_source.py -v
```

Expected: 2 passed, 2 skipped.

- [ ] **Step 6: Commit**

```bash
git add src/curbcam/camera/usb_source.py src/curbcam/camera/rtsp_source.py tests/unit/camera/test_usb_source.py tests/unit/camera/test_rtsp_source.py
git commit -m "feat(camera): UsbSource and RtspSource with reconnect logic"
```

---

## Task 12: Camera factory + picamera2 lazy adapter

**Files:**
- Create: `src/curbcam/camera/picamera2_source.py`
- Create: `src/curbcam/camera/factory.py`
- Create: `tests/unit/camera/test_factory.py`

- [ ] **Step 1: Write `src/curbcam/camera/picamera2_source.py`**

```python
"""Raspberry Pi Camera Module via picamera2 (libcamera).

picamera2 is Linux/ARM-only. We import it inside ``open()`` so unit
tests on dev laptops don't need the dependency installed. The CLI's
camera factory raises a clear error if the user picks ``picamera2:N``
on a system without the library.
"""
from __future__ import annotations

import time

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
        self._cam = None   # type: ignore[var-annotated]

    def open(self) -> None:
        if self._cam is not None:
            return
        try:
            from picamera2 import Picamera2   # type: ignore[import-not-found]
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
```

- [ ] **Step 2: Write the failing factory test**

```python
# tests/unit/camera/test_factory.py
from pathlib import Path

import pytest

from curbcam.camera.factory import camera_from_source
from curbcam.camera.file_replay import FileReplaySource


def test_factory_returns_file_replay_for_file_source(tmp_path: Path) -> None:
    # Create a single dummy frame so FileReplaySource.open() can probe shape.
    import cv2
    import numpy as np
    cv2.imwrite(str(tmp_path / "0001.jpg"), np.zeros((10, 10, 3), dtype=np.uint8))

    cam = camera_from_source(
        f"file:{tmp_path}", resolution=(640, 480), fps_target=10.0
    )
    assert isinstance(cam, FileReplaySource)


def test_factory_routes_usb_prefix() -> None:
    from curbcam.camera.usb_source import UsbSource
    cam = camera_from_source("usb:0", resolution=(640, 480), fps_target=15.0)
    assert isinstance(cam, UsbSource)


def test_factory_routes_rtsp_prefix() -> None:
    from curbcam.camera.rtsp_source import RtspSource
    cam = camera_from_source(
        "rtsp://example.invalid/stream", resolution=(640, 480), fps_target=15.0
    )
    assert isinstance(cam, RtspSource)


def test_factory_routes_picamera2_prefix() -> None:
    from curbcam.camera.picamera2_source import Picamera2Source
    cam = camera_from_source("picamera2:0", resolution=(640, 480), fps_target=15.0)
    assert isinstance(cam, Picamera2Source)


def test_factory_raises_on_unknown_prefix() -> None:
    with pytest.raises(ValueError, match="Unknown camera source"):
        camera_from_source("magic:thing", resolution=(640, 480), fps_target=15.0)
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run pytest tests/unit/camera/test_factory.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'curbcam.camera.factory'`.

- [ ] **Step 4: Write `src/curbcam/camera/factory.py`**

```python
"""Map a config string to a Camera implementation.

Format examples:
    picamera2:0
    picamera2:1
    usb:0                      (integer device index)
    usb:/dev/video0            (string device path)
    rtsp://user:pw@host:554/s
    file:./fixtures/sample
"""
from __future__ import annotations

from pathlib import Path

from curbcam.camera.base import Camera
from curbcam.camera.file_replay import FileReplaySource
from curbcam.camera.picamera2_source import Picamera2Source
from curbcam.camera.rtsp_source import RtspSource
from curbcam.camera.usb_source import UsbSource


def camera_from_source(
    source: str,
    *,
    resolution: tuple[int, int],
    fps_target: float,
) -> Camera:
    if source.startswith("picamera2:"):
        idx = int(source.split(":", 1)[1])
        return Picamera2Source(idx, resolution=resolution, fps_target=fps_target)
    if source.startswith("usb:"):
        rest = source.split(":", 1)[1]
        device: str | int = int(rest) if rest.isdigit() else rest
        return UsbSource(device, resolution=resolution, fps_target=fps_target)
    if source.startswith("rtsp://") or source.startswith("rtsps://"):
        return RtspSource(source, resolution=resolution, fps_target=fps_target)
    if source.startswith("file:"):
        path = Path(source.split(":", 1)[1])
        return FileReplaySource(path, fps_target=fps_target, loop=True)
    raise ValueError(f"Unknown camera source: {source!r}")
```

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/unit/camera/test_factory.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/curbcam/camera/picamera2_source.py src/curbcam/camera/factory.py tests/unit/camera/test_factory.py
git commit -m "feat(camera): Picamera2Source (lazy import) + camera_from_source factory"
```

---

## Task 13: In-process event bus

**Files:**
- Create: `src/curbcam/pipeline/__init__.py`
- Create: `src/curbcam/pipeline/events.py`
- Create: `tests/unit/pipeline/__init__.py`
- Create: `tests/unit/pipeline/test_events.py`

- [ ] **Step 1: Write `src/curbcam/pipeline/__init__.py`**

```python
"""Runner + event-bus that wires camera → detector → storage."""
from curbcam.pipeline.events import EventBus, EventEnvelope

__all__ = ["EventBus", "EventEnvelope"]
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/pipeline/test_events.py
import asyncio

import pytest

from curbcam.pipeline.events import EventBus, EventEnvelope


@pytest.mark.asyncio
async def test_subscriber_receives_published_event() -> None:
    bus = EventBus()
    sub = bus.subscribe()

    bus.publish(EventEnvelope(kind="event", payload={"speed_kph": 42.0}))

    got = await asyncio.wait_for(sub.get(), timeout=1.0)
    assert got.kind == "event"
    assert got.payload["speed_kph"] == 42.0


@pytest.mark.asyncio
async def test_multiple_subscribers_each_receive_one_copy() -> None:
    bus = EventBus()
    a = bus.subscribe()
    b = bus.subscribe()

    bus.publish(EventEnvelope(kind="event", payload={"speed_kph": 30.0}))

    got_a = await asyncio.wait_for(a.get(), timeout=1.0)
    got_b = await asyncio.wait_for(b.get(), timeout=1.0)
    assert got_a.payload["speed_kph"] == 30.0
    assert got_b.payload["speed_kph"] == 30.0


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery() -> None:
    bus = EventBus()
    sub = bus.subscribe()
    bus.unsubscribe(sub)

    bus.publish(EventEnvelope(kind="event", payload={"x": 1}))

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(sub.get(), timeout=0.1)


@pytest.mark.asyncio
async def test_publish_is_thread_safe_via_loop_call_soon_threadsafe() -> None:
    """The runner thread will call publish_threadsafe() from outside the loop."""
    bus = EventBus()
    bus.bind_loop(asyncio.get_running_loop())
    sub = bus.subscribe()

    import threading
    threading.Thread(
        target=lambda: bus.publish_threadsafe(EventEnvelope(kind="event", payload={}))
    ).start()

    got = await asyncio.wait_for(sub.get(), timeout=1.0)
    assert got.kind == "event"
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run pytest tests/unit/pipeline/test_events.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'curbcam.pipeline.events'`.

- [ ] **Step 4: Write `src/curbcam/pipeline/events.py`**

```python
"""In-process pub-sub for finalised events and pipeline status.

Used by MVP-2's SSE endpoint and by future v0.2 webhook/MQTT plugins.
A single fanout point (publish) so adding subscribers is additive.

Threading: publish() must be called from inside the asyncio loop;
publish_threadsafe() may be called from any thread (the detector thread
typically) and bridges into the loop via call_soon_threadsafe.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal


EventKind = Literal["event", "stats", "calibration_changed", "settings_changed"]


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    kind: EventKind
    payload: dict[str, Any] = field(default_factory=dict)


class EventBus:
    def __init__(self) -> None:
        self._subs: list[asyncio.Queue[EventEnvelope]] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue[EventEnvelope]:
        q: asyncio.Queue[EventEnvelope] = asyncio.Queue()
        self._subs.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[EventEnvelope]) -> None:
        try:
            self._subs.remove(q)
        except ValueError:
            pass

    def publish(self, env: EventEnvelope) -> None:
        """Call from inside the asyncio loop."""
        for q in self._subs:
            q.put_nowait(env)

    def publish_threadsafe(self, env: EventEnvelope) -> None:
        """Call from any thread. Requires ``bind_loop`` to have been called."""
        if self._loop is None:
            # No loop bound yet → drop (CLI usage without async server).
            return
        self._loop.call_soon_threadsafe(self.publish, env)
```

- [ ] **Step 5: Create `tests/unit/pipeline/__init__.py` and run tests**

```python
# tests/unit/pipeline/__init__.py
```

```bash
uv run pytest tests/unit/pipeline/test_events.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/curbcam/pipeline/__init__.py src/curbcam/pipeline/events.py tests/unit/pipeline/
git commit -m "feat(pipeline): EventBus with thread-safe publish"
```

---

## Task 14: Pipeline runner

**Files:**
- Create: `src/curbcam/pipeline/runner.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_pipeline_runner.py`
- Create: `tests/integration/fixtures/__init__.py`
- Create: `tests/integration/fixtures/synthetic_run.py`

- [ ] **Step 1: Write the synthetic-run fixture generator**

```python
# tests/integration/fixtures/synthetic_run.py
"""Generate a directory of JPEGs simulating a vehicle moving L→R.

10 frames, black background, white 40x40 rectangle moving from x=100 to
x=460 (40 px per frame). Suitable for FileReplaySource consumption.
"""
from __future__ import annotations

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
```

- [ ] **Step 2: Write the failing integration test**

```python
# tests/integration/test_pipeline_runner.py
import time
from pathlib import Path

import pytest

from curbcam.camera.file_replay import FileReplaySource
from curbcam.config.schema import (
    CameraSettings,
    DetectorSettings,
    RetentionSettings,
    ServerSettings,
    Settings,
)
from curbcam.pipeline.events import EventBus
from curbcam.pipeline.runner import PipelineRunner
from curbcam.storage.db import Database
from curbcam.storage.models import Base
from curbcam.storage.repositories import CalibrationRepo, EventRepo
from curbcam.storage.media import MediaWriter
from tests.integration.fixtures.synthetic_run import write_synthetic_run


@pytest.mark.timeout(30)
def test_runner_processes_synthetic_run_and_writes_an_event(tmp_path: Path) -> None:
    # Arrange: synthetic L→R run, a calibration, fresh DB and media root.
    run_dir = tmp_path / "run"
    write_synthetic_run(run_dir, frames=10, step_px=40)

    media_root = tmp_path / "media"
    media_root.mkdir()
    db = Database.for_sqlite_path(tmp_path / "events.sqlite")
    Base.metadata.create_all(db.engine)

    cal_repo = CalibrationRepo(db)
    cal_repo.save_new_active(
        mm_per_px_l2r=10.0, mm_per_px_r2l=10.0,
        reference_distance_mm=400.0, reference_points_json="[]",
    )

    settings = Settings(
        camera=CameraSettings(source="file:dummy", resolution=(640, 480), fps_target=60.0),
        detector=DetectorSettings(min_area_px=400, min_track_frames=3, max_dist_px=80),
        retention=RetentionSettings(),
        server=ServerSettings(min_event_speed_kph=0.0),
    )

    camera = FileReplaySource(run_dir, fps_target=60.0, loop=False)
    runner = PipelineRunner(
        camera=camera,
        db=db,
        event_repo=EventRepo(db),
        calibration_repo=cal_repo,
        media=MediaWriter(media_root),
        bus=EventBus(),
        settings=settings,
    )

    # Act: run until the source is exhausted.
    runner.run_until_camera_exhausted()

    # Assert: exactly one event was persisted with L2R direction.
    with db.session() as s:
        from curbcam.storage.models import Event
        events = s.query(Event).all()
        assert len(events) == 1, f"expected 1 event, got {len(events)}"
        e = events[0]
        assert e.direction == "L2R"
        assert e.speed_kph > 0

    # Assert: media files were written.
    assert (media_root / e.image_path).exists()
    assert (media_root / e.thumb_path).exists()


@pytest.mark.timeout(30)
def test_runner_processes_r2l_run_with_r2l_calibration(tmp_path: Path) -> None:
    """End-to-end check that mm_per_px_r2l is the value actually used for R2L tracks."""
    run_dir = tmp_path / "run"
    write_synthetic_run(run_dir, frames=10, step_px=40, direction="R2L")

    media_root = tmp_path / "media"
    media_root.mkdir()
    db = Database.for_sqlite_path(tmp_path / "events.sqlite")
    Base.metadata.create_all(db.engine)

    cal_repo = CalibrationRepo(db)
    # L2R cal is intentionally junk; if pipeline confuses directions the
    # produced speed will be wildly wrong.
    cal_repo.save_new_active(
        mm_per_px_l2r=999.0, mm_per_px_r2l=10.0,
        reference_distance_mm=400.0, reference_points_json="[]",
    )

    settings = Settings(
        camera=CameraSettings(source="file:dummy", resolution=(640, 480), fps_target=60.0),
        detector=DetectorSettings(min_area_px=400, min_track_frames=3, max_dist_px=80),
        retention=RetentionSettings(),
        server=ServerSettings(min_event_speed_kph=0.0),
    )

    camera = FileReplaySource(run_dir, fps_target=60.0, loop=False)
    runner = PipelineRunner(
        camera=camera, db=db,
        event_repo=EventRepo(db), calibration_repo=cal_repo,
        media=MediaWriter(media_root), bus=EventBus(),
        settings=settings,
    )
    runner.run_until_camera_exhausted()

    with db.session() as s:
        from curbcam.storage.models import Event
        events = s.query(Event).all()
        assert len(events) == 1
        e = events[0]
        assert e.direction == "R2L"
        # With mm_per_px_r2l=10.0, sane speed should be a small two-digit kph,
        # nowhere near the 999-multiplier l2r calibration would produce.
        assert 0 < e.speed_kph < 500


@pytest.mark.timeout(30)
def test_runner_skips_persistence_when_no_active_calibration(tmp_path: Path) -> None:
    """No crash, no event row when a track finalises without a calibration."""
    run_dir = tmp_path / "run"
    write_synthetic_run(run_dir, frames=10, step_px=40)

    media_root = tmp_path / "media"
    media_root.mkdir()
    db = Database.for_sqlite_path(tmp_path / "events.sqlite")
    Base.metadata.create_all(db.engine)

    settings = Settings(
        camera=CameraSettings(source="file:dummy", resolution=(640, 480), fps_target=60.0),
        detector=DetectorSettings(min_area_px=400, min_track_frames=3, max_dist_px=80),
        retention=RetentionSettings(),
        server=ServerSettings(min_event_speed_kph=0.0),
    )

    camera = FileReplaySource(run_dir, fps_target=60.0, loop=False)
    runner = PipelineRunner(
        camera=camera, db=db,
        event_repo=EventRepo(db), calibration_repo=CalibrationRepo(db),
        media=MediaWriter(media_root), bus=EventBus(),
        settings=settings,
    )
    runner.run_until_camera_exhausted()   # must not raise

    with db.session() as s:
        from curbcam.storage.models import Event
        assert s.query(Event).count() == 0
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run pytest tests/integration/test_pipeline_runner.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'curbcam.pipeline.runner'`.

- [ ] **Step 4: Write `src/curbcam/pipeline/runner.py`**

```python
"""The single orchestrator: camera → detector → storage.

Two flavours of operation:
- ``run_until_camera_exhausted()`` — synchronous, used by the CLI's
  ``curbcam detect`` command and by tests with a FileReplaySource.
- ``run_in_background_thread()`` — used by the MVP-2 web server. Returns
  a started thread; .stop() to ask it to wind down.

Per design spec §4.3: this is the ONLY module that wires the three
collaborators. The detector knows nothing about storage; storage knows
nothing about cameras.
"""
from __future__ import annotations

import datetime as dt
import logging
import threading
import time

import cv2

from curbcam.camera.base import Camera
from curbcam.config.schema import Settings
from curbcam.detector.calibration import speed_from_track
from curbcam.detector.motion import find_motion
from curbcam.detector.tracker import Tracker
from curbcam.pipeline.events import EventBus, EventEnvelope
from curbcam.storage.db import Database
from curbcam.storage.media import MediaWriter
from curbcam.storage.repositories import CalibrationRepo, EventRepo


log = logging.getLogger(__name__)


class PipelineRunner:
    def __init__(
        self,
        *,
        camera: Camera,
        db: Database,
        event_repo: EventRepo,
        calibration_repo: CalibrationRepo,
        media: MediaWriter,
        bus: EventBus,
        settings: Settings,
    ) -> None:
        self._camera = camera
        self._db = db
        self._events = event_repo
        self._calibrations = calibration_repo
        self._media = media
        self._bus = bus
        self._settings = settings
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        self._tracker = Tracker(
            max_dist_px=settings.detector.max_dist_px,
            min_track_frames=settings.detector.min_track_frames,
        )

    def run_until_camera_exhausted(self) -> None:
        self._camera.open()
        try:
            prev_gray = None
            last_full_frame = None
            while not self._stop.is_set():
                got = self._camera.read()
                if got is None:
                    break
                frame_bgr, ts = got
                last_full_frame = frame_bgr
                curr_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
                if prev_gray is not None:
                    self._process_frame(prev_gray, curr_gray, frame_bgr, frame_ts=ts)
                prev_gray = curr_gray
            # Source exhausted — flush any in-flight track.
            if last_full_frame is not None:
                for track in self._tracker.flush():
                    self._persist_track(track, last_full_frame)
        finally:
            self._camera.close()

    def run_in_background_thread(self) -> threading.Thread:
        if self._thread is not None and self._thread.is_alive():
            return self._thread
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop_with_reconnect, name="curbcam-runner", daemon=True
        )
        self._thread.start()
        return self._thread

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _loop_with_reconnect(self) -> None:
        """Reconnect loop for persistent sources; one-shot for finite sources.

        A live camera (USB, RTSP, picamera2, looping replay) has
        ``is_persistent = True``: when read() returns None we treat it
        as a transient failure, sleep briefly, and reopen. A finite
        source (non-looping FileReplaySource) has
        ``is_persistent = False``: when run_until_camera_exhausted
        returns normally, we exit the loop. Either way, exceptions are
        logged and retried for persistent sources only.
        """
        while not self._stop.is_set():
            try:
                self.run_until_camera_exhausted()
            except Exception:
                log.exception("Pipeline crashed")
                if not self._camera.is_persistent:
                    return
                time.sleep(2.0)
                continue
            if not self._camera.is_persistent:
                return
            time.sleep(0.5)

    # -- internals --

    def _process_frame(self, prev_gray, curr_gray, frame_bgr, *, frame_ts: float) -> None:
        detections = find_motion(
            prev_gray,
            curr_gray,
            min_area_px=self._settings.detector.min_area_px,
            crop=self._settings.detector.crop,
            frame_ts=frame_ts,
        )
        finalised = self._tracker.update(detections)
        for track in finalised:
            self._persist_track(track, frame_bgr)

    def _persist_track(self, track, last_frame_bgr) -> None:
        cal = self._calibrations.get_active()
        if cal is None:
            log.info("Track finalised but no active calibration; skipping")
            return
        from curbcam.detector.calibration import Calibration as CalDC
        cal_dc = CalDC(mm_per_px_l2r=float(cal.mm_per_px_l2r),
                       mm_per_px_r2l=float(cal.mm_per_px_r2l))
        speed = speed_from_track(track, cal_dc)
        if speed is None:
            return
        if speed < self._settings.server.min_event_speed_kph:
            log.info("Track below min_event_speed_kph (%.1f); skipping", speed)
            return

        ts_utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        with self._db.session() as s:
            from curbcam.storage.models import Event
            ev = Event(
                ts_utc=ts_utc,
                speed_kph=float(speed),
                direction=track.direction or "L2R",
                frame_count=len(track.detections),
                track_len_px=int(
                    abs(track.detections[-1].centroid[0] - track.detections[0].centroid[0])
                ),
                image_path="",
                thumb_path="",
                calibration_id=cal.id,
            )
            s.add(ev)
            s.flush()
            rel_full, rel_thumb = self._media.save_event_image(
                frame=last_frame_bgr,
                event_id=ev.id,
                ts_utc=ts_utc,
                speed_kph=float(speed),
                direction=ev.direction,
            )
            ev.image_path = rel_full
            ev.thumb_path = rel_thumb
            s.commit()
            event_id = ev.id

        self._bus.publish_threadsafe(
            EventEnvelope(
                kind="event",
                payload={
                    "id": event_id,
                    "speed_kph": float(speed),
                    "direction": track.direction,
                    "image_path": rel_full,
                    "thumb_path": rel_thumb,
                    "ts_utc": ts_utc.isoformat(),
                },
            )
        )
        log.info("Event %d persisted: %.1f kph %s", event_id, speed, track.direction)
```

- [ ] **Step 5: Create `tests/integration/__init__.py` and `tests/integration/fixtures/__init__.py`**

```python
# tests/integration/__init__.py
```

```python
# tests/integration/fixtures/__init__.py
```

- [ ] **Step 6: Run integration test**

```bash
uv run pytest tests/integration/test_pipeline_runner.py -v
```

Expected: 1 passed. If it fails because `pytest-timeout` isn't installed, add it to dev deps and re-run:

```bash
uv add --dev pytest-timeout
uv run pytest tests/integration/test_pipeline_runner.py -v
```

- [ ] **Step 7: Commit**

```bash
git add src/curbcam/pipeline/runner.py tests/integration/ pyproject.toml uv.lock
git commit -m "feat(pipeline): PipelineRunner end-to-end with integration test"
```

---

## Task 15: CLI entry point

**Files:**
- Create: `src/curbcam/cli.py`
- Create: `tests/integration/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_cli.py
import subprocess
import sys
from pathlib import Path

import pytest

from tests.integration.fixtures.synthetic_run import write_synthetic_run


@pytest.mark.timeout(60)
def test_cli_detect_writes_events_to_sqlite(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    write_synthetic_run(run_dir, frames=10, step_px=40)

    data_dir = tmp_path / "data"
    media_dir = tmp_path / "media"
    config_path = tmp_path / "curbcam.yaml"

    # Seed a calibration via the CLI itself (single-command setup).
    result = subprocess.run(
        [
            sys.executable, "-m", "curbcam.cli", "calibrate",
            "--mm-per-px-l2r", "10.0",
            "--mm-per-px-r2l", "10.0",
            "--reference-distance-mm", "400",
            "--data-dir", str(data_dir),
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    # Run the detect command against the file source.
    result = subprocess.run(
        [
            sys.executable, "-m", "curbcam.cli", "detect",
            "--config", str(config_path),
            "--data-dir", str(data_dir),
            "--media-dir", str(media_dir),
            "--camera", f"file:{run_dir}",
            "--min-event-speed-kph", "0",
            "--once",
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    # Assert at least one event was written to the DB.
    import sqlite3
    db_path = data_dir / "curbcam.sqlite"
    assert db_path.exists()
    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert count >= 1
    finally:
        conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/integration/test_cli.py -v
```

Expected: FAIL because the CLI module doesn't exist yet.

- [ ] **Step 3: Write `src/curbcam/cli.py`**

```python
"""curbcam command-line interface.

Subcommands:
    curbcam detect      Run the pipeline against a configured camera.
    curbcam calibrate   Insert a new active calibration row directly.
    curbcam db init     Create/upgrade the SQLite schema.
"""
from __future__ import annotations

import logging
from pathlib import Path

import typer

from curbcam.camera.factory import camera_from_source
from curbcam.config.schema import Settings
from curbcam.config.store import ConfigStore
from curbcam.pipeline.events import EventBus
from curbcam.pipeline.runner import PipelineRunner
from curbcam.storage.db import Database
from curbcam.storage.media import MediaWriter
from curbcam.storage.models import Base
from curbcam.storage.repositories import CalibrationRepo, EventRepo


app = typer.Typer(help="curbcam — speed camera CLI", no_args_is_help=True)


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-5s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


@app.command()
def detect(
    config: Path = typer.Option(Path("curbcam.yaml"), help="Path to YAML config"),
    data_dir: Path = typer.Option(Path("./data"), help="Directory for SQLite DB"),
    media_dir: Path = typer.Option(Path("./media"), help="Directory for event JPEGs"),
    camera: str | None = typer.Option(None, help="Override camera source string"),
    min_event_speed_kph: float | None = typer.Option(None),
    once: bool = typer.Option(False, help="Run until camera exhausts, then exit"),
) -> None:
    """Run the pipeline."""
    store = ConfigStore(config)
    settings = store.load()
    if camera is not None:
        settings = settings.model_copy(update={
            "camera": settings.camera.model_copy(update={"source": camera}),
        })
    if min_event_speed_kph is not None:
        settings = settings.model_copy(update={
            "server": settings.server.model_copy(
                update={"min_event_speed_kph": min_event_speed_kph}
            ),
        })

    _setup_logging(settings.server.log_level)

    db = Database.for_sqlite_path(data_dir / "curbcam.sqlite")
    Base.metadata.create_all(db.engine)   # idempotent; alembic-managed in prod

    cam = camera_from_source(
        settings.camera.source,
        resolution=settings.camera.resolution,
        fps_target=settings.camera.fps_target,
    )

    runner = PipelineRunner(
        camera=cam,
        db=db,
        event_repo=EventRepo(db),
        calibration_repo=CalibrationRepo(db),
        media=MediaWriter(media_dir),
        bus=EventBus(),
        settings=settings,
    )

    if once:
        runner.run_until_camera_exhausted()
        return

    thread = runner.run_in_background_thread()
    try:
        thread.join()
    except KeyboardInterrupt:
        runner.stop()


@app.command()
def calibrate(
    mm_per_px_l2r: float = typer.Option(..., "--mm-per-px-l2r"),
    mm_per_px_r2l: float = typer.Option(..., "--mm-per-px-r2l"),
    reference_distance_mm: float = typer.Option(..., "--reference-distance-mm"),
    notes: str | None = typer.Option(None),
    data_dir: Path = typer.Option(Path("./data")),
) -> None:
    """Write a new active calibration directly (CLI bootstrap before MVP-2 UI)."""
    db = Database.for_sqlite_path(data_dir / "curbcam.sqlite")
    Base.metadata.create_all(db.engine)
    repo = CalibrationRepo(db)
    cal = repo.save_new_active(
        mm_per_px_l2r=mm_per_px_l2r,
        mm_per_px_r2l=mm_per_px_r2l,
        reference_distance_mm=reference_distance_mm,
        reference_points_json="[]",
        notes=notes,
    )
    typer.echo(f"Active calibration #{cal.id} written.")


db_app = typer.Typer(help="Database admin")
app.add_typer(db_app, name="db")


@db_app.command("init")
def db_init(data_dir: Path = typer.Option(Path("./data"))) -> None:
    """Create the SQLite schema (idempotent)."""
    db = Database.for_sqlite_path(data_dir / "curbcam.sqlite")
    Base.metadata.create_all(db.engine)
    typer.echo(f"Schema initialised at {data_dir / 'curbcam.sqlite'}")


def main() -> None:   # pragma: no cover
    app()


if __name__ == "__main__":   # pragma: no cover
    main()
```

- [ ] **Step 4: Run the CLI test**

```bash
uv run pytest tests/integration/test_cli.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Manual smoke against a real synthetic run**

Write a tiny helper script (more robust than `python -c` with multi-line
strings, especially on PowerShell):

```python
# scripts/make_sample_run.py
from pathlib import Path

from tests.integration.fixtures.synthetic_run import write_synthetic_run

write_synthetic_run(Path("./fixtures/sample_run"), frames=12, step_px=40)
print("Wrote 12 sample frames to ./fixtures/sample_run")
```

Then run it:

```bash
cd D:/curbcam
mkdir -p scripts
# (paste the script above into scripts/make_sample_run.py)
uv run python scripts/make_sample_run.py
uv run curbcam calibrate --mm-per-px-l2r 10 --mm-per-px-r2l 10 --reference-distance-mm 400
uv run curbcam detect --camera file:./fixtures/sample_run --min-event-speed-kph 0 --once
```

Expected: log line `Event 1 persisted: <N>.<N> kph L2R`, plus a JPEG under `media/events/...`.

- [ ] **Step 6: Commit**

```bash
git add src/curbcam/cli.py tests/integration/test_cli.py
git commit -m "feat(cli): curbcam {detect,calibrate,db init} commands"
```

---

## Task 16: Retention sweeper

**Files:**
- Create: `src/curbcam/storage/retention.py`
- Create: `tests/unit/storage/test_retention.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/storage/test_retention.py
import datetime as dt
from pathlib import Path

import pytest

from curbcam.storage import Database
from curbcam.storage.models import Base, Event
from curbcam.storage.retention import RetentionSweeper


@pytest.fixture
def populated(tmp_path: Path) -> tuple[Database, Path]:
    db = Database.for_sqlite_path(tmp_path / "r.sqlite")
    Base.metadata.create_all(db.engine)
    media = tmp_path / "media"
    media.mkdir()
    # Seed 5 events with associated files.
    with db.session() as s:
        for i in range(5):
            rel = f"events/2026/05/28/event_{i}.jpg"
            (media / rel).parent.mkdir(parents=True, exist_ok=True)
            (media / rel).write_bytes(b"x" * 100_000)   # 100 KB
            s.add(
                Event(
                    ts_utc=dt.datetime(2026, 5, 28, 12, i, 0),
                    speed_kph=30.0,
                    direction="L2R",
                    frame_count=10,
                    track_len_px=200,
                    image_path=rel,
                    thumb_path=rel.replace("events/", "thumbs/"),
                    calibration_id=None,
                )
            )
        s.commit()
    return db, media


def test_sweeper_enforces_max_events_per_day(populated: tuple[Database, Path]) -> None:
    db, media = populated
    sweeper = RetentionSweeper(db=db, media_root=media,
                               max_events_per_day=2, max_total_disk_mb=10_000)
    deleted = sweeper.sweep()
    assert deleted >= 3
    with db.session() as s:
        remaining = s.query(Event).count()
        assert remaining == 2


def test_sweeper_enforces_max_total_disk(populated: tuple[Database, Path]) -> None:
    db, media = populated
    # 5 files × 100 KB = 500 KB ≈ 0.5 MB; cap at 0 MB to force purge.
    sweeper = RetentionSweeper(db=db, media_root=media,
                               max_events_per_day=10_000, max_total_disk_mb=0)
    deleted = sweeper.sweep()
    assert deleted >= 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/storage/test_retention.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'curbcam.storage.retention'`.

- [ ] **Step 3: Write `src/curbcam/storage/retention.py`**

```python
"""Single retention sweeper.

Two policies enforced (centralised — design spec §7.2):
1. ``max_events_per_day``: per-day count cap.
2. ``max_total_disk_mb``: total media-folder size cap (oldest events purged first).

The sweeper deletes the DB row AND the JPEG + thumbnail. It is safe to
run repeatedly (no-op if everything is under cap). Returns count of
events deleted.
"""
from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

from sqlalchemy import func

from curbcam.storage.db import Database
from curbcam.storage.models import Event


log = logging.getLogger(__name__)


class RetentionSweeper:
    def __init__(
        self,
        *,
        db: Database,
        media_root: Path,
        max_events_per_day: int,
        max_total_disk_mb: int,
    ) -> None:
        self._db = db
        self._media_root = media_root
        self._max_per_day = max_events_per_day
        self._max_disk_bytes = max_total_disk_mb * 1024 * 1024

    def sweep(self) -> int:
        deleted = 0
        deleted += self._enforce_per_day_cap()
        deleted += self._enforce_disk_cap()
        return deleted

    def _enforce_per_day_cap(self) -> int:
        deleted = 0
        with self._db.session() as s:
            day_counts = (
                s.query(func.date(Event.ts_utc).label("day"), func.count(Event.id))
                .group_by("day")
                .having(func.count(Event.id) > self._max_per_day)
                .all()
            )
            for day, _count in day_counts:
                victims = (
                    s.query(Event)
                    .filter(func.date(Event.ts_utc) == day)
                    .order_by(Event.ts_utc.asc())
                    .all()
                )
                to_delete = victims[: len(victims) - self._max_per_day]
                for ev in to_delete:
                    self._delete_files(ev)
                    s.delete(ev)
                    deleted += 1
            s.commit()
        return deleted

    def _enforce_disk_cap(self) -> int:
        deleted = 0
        with self._db.session() as s:
            while True:
                total = self._total_media_bytes()
                if total <= self._max_disk_bytes:
                    break
                oldest = (
                    s.query(Event).order_by(Event.ts_utc.asc()).first()
                )
                if oldest is None:
                    break
                self._delete_files(oldest)
                s.delete(oldest)
                s.commit()
                deleted += 1
        return deleted

    def _total_media_bytes(self) -> int:
        total = 0
        for path in self._media_root.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
        return total

    def _delete_files(self, ev: Event) -> None:
        for rel in (ev.image_path, ev.thumb_path):
            if not rel:
                continue
            p = self._media_root / rel
            try:
                p.unlink(missing_ok=True)
            except OSError:
                log.exception("Failed to delete %s", p)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/storage/test_retention.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/curbcam/storage/retention.py tests/unit/storage/test_retention.py
git commit -m "feat(storage): RetentionSweeper for per-day + total-disk caps"
```

---

## Task 17: Lint + full suite green check

**Files:**
- No new files.

- [ ] **Step 1: Run ruff**

```bash
cd D:/curbcam
uv run ruff check .
uv run ruff format --check .
```

Expected: no findings. Fix any reported issues inline before moving on (use `uv run ruff format .` to autoformat, then re-run check).

- [ ] **Step 2: Run mypy strict on the package**

```bash
uv run mypy src/curbcam
```

Expected: `Success: no issues found`. Fix any type errors inline; do not suppress with `# type: ignore` unless documented.

- [ ] **Step 3: Run the full test suite**

```bash
uv run pytest -v --cov=curbcam --cov-report=term-missing
```

Expected: all passed (USB / RTSP tests skipped without hardware). Coverage on `src/curbcam/` should be ≥ 85% — anything lower is a sign of a missing test that this plan didn't cover.

- [ ] **Step 4: Commit any lint fixes**

```bash
git status                     # may show clean
git add -A
git commit -m "chore: lint/type fixes from MVP-1 final pass" || true
```

---

## Task 18: README quick-start for MVP-1

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace `README.md` body**

```markdown
# curbcam

A modern, neighbor-friendly speed camera for Raspberry Pi.

Detects moving vehicles, calculates speed, stores results — all configurable
through a web UI (coming in MVP-2) with a guided calibration wizard. No SSH
required for normal use.

**Status:** MVP-1 (headless detector + CLI) — see
[`docs/specs/2026-05-28-curbcam-design.md`](docs/specs/2026-05-28-curbcam-design.md)
for the full design.

## What works today (MVP-1)

A command-line speed-camera pipeline:

```bash
# 1. Install (dev environment — Pi-friendly Docker image is MVP-3)
git clone https://github.com/PatientVibes/curbcam
cd curbcam
uv venv && uv pip install -e ".[dev]"

# 2. Seed a calibration (one-time; MVP-2 replaces this with a web wizard)
uv run curbcam calibrate \
    --mm-per-px-l2r 41.3 --mm-per-px-r2l 41.5 \
    --reference-distance-mm 4700

# 3. Run the detector against a camera or a directory of frames
uv run curbcam detect --camera usb:0
# or
uv run curbcam detect --camera rtsp://user:pw@cam.local/stream
# or (dev / debugging)
uv run curbcam detect --camera file:./fixtures/sample_run --once
```

Events land in `./data/curbcam.sqlite`; thumbnails and full-frame JPEGs in
`./media/`.

## Camera sources

| Prefix | Example | Notes |
|---|---|---|
| `picamera2:` | `picamera2:0` | Raspberry Pi Camera Module via libcamera. Requires `uv pip install '.[picamera2]'` on the Pi. |
| `usb:` | `usb:0` or `usb:/dev/video0` | Any V4L2 / DirectShow webcam OpenCV can open. |
| `rtsp://` | `rtsp://user:pw@host/stream` | IP cameras. Stores credentials in plaintext — prefer the env-var override (see below). |
| `file:` | `file:./fixtures/sample_run` | Replays a directory of JPEGs. Dev + tests. |

### Avoiding plaintext RTSP credentials

```bash
export CURBCAM_CAMERA__SOURCE="rtsp://user:pw@host/stream"
uv run curbcam detect       # no credentials in the YAML config
```

## Before you install

Speed cameras inherently capture people, vehicles, and license plates in
public or semi-public spaces. The legal status of doing so varies by
jurisdiction (GDPR in the EU, state-by-state in the US, etc.). **Check
your local laws before pointing this at a public road or shared space.**
This project's defaults are private-network-only — nothing is exposed
externally, no data leaves your device, no license-plate OCR is shipped.
See the design spec's *Responsible Use & Privacy* section (§15) for the
project's full stance.

## Inspiration

Inspired by [pageauc/speed-camera](https://github.com/pageauc/speed-camera),
re-implemented from scratch with a focus on installability, wizard-driven
setup, and a single Docker-based deployment path (MVP-3).

## License

MIT.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: MVP-1 quick-start in README"
```

---

## Task 19: Push and tag MVP-1

**Files:**
- None.

- [ ] **Step 1: Push to origin**

```bash
git push origin main
```

- [ ] **Step 2: Tag the MVP-1 milestone**

```bash
git tag -a v0.1.0-mvp-1 -m "MVP-1: headless detector + CLI"
git push origin v0.1.0-mvp-1
```

- [ ] **Step 3: Verify the tag on GitHub**

```bash
gh release view v0.1.0-mvp-1 2>&1 || echo "Tag pushed; release page can be created later"
```

Expected: tag visible at https://github.com/PatientVibes/curbcam/tags

---

## What ships at the end of MVP-1

After Task 19 the repository will:

- Have a single `curbcam` CLI with `detect`, `calibrate`, and `db init`
  subcommands.
- Detect motion from picamera2, USB, RTSP, or a directory of frames.
- Calculate per-event speed against an active calibration and persist
  events + annotated JPEGs + thumbnails.
- Be testable end-to-end via the `FileReplaySource` without any hardware.
- Have unit coverage on detector, config, storage; integration coverage
  on the pipeline runner and the CLI.
- Be lint-clean (ruff) and type-clean (mypy strict).

The detector half of the design spec is fully realised; the server half
(MVP-2) and the deployment half (MVP-3) are the next two plans.
