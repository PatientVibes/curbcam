import pytest

from curbcam.detector.calibration import Calibration, speed_from_track
from curbcam.detector.types import Detection, TrackedObject


def make_track(pixels_traveled: int, dt_seconds: float, direction: str) -> TrackedObject:
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


def test_speed_from_track_returns_none_when_dt_not_positive() -> None:
    """When two detections share the same timestamp, dt is zero → None."""
    cal = Calibration(mm_per_px_l2r=50.0, mm_per_px_r2l=50.0)
    track = TrackedObject(
        id="t1",
        detections=[
            Detection(bbox=(0, 0, 10, 10), centroid=(100, 100), area_px=100, frame_ts=1.0),
            Detection(bbox=(0, 0, 10, 10), centroid=(200, 100), area_px=100, frame_ts=1.0),
        ],
        direction="L2R",
        speed_kph=None,
    )
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
