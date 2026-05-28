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

    crop = (300, 0, 640, 480)  # x_left, y_upper, x_right, y_lower
    detections = find_motion(prev, curr, min_area_px=500, crop=crop, frame_ts=1.5)
    assert detections == []


def test_find_motion_uses_supplied_frame_ts() -> None:
    """frame_ts must reflect capture time, not compute time."""
    prev = _to_gray(frame_with_white_rect(x=100, y=200, w=40, h=40))
    curr = _to_gray(frame_with_white_rect(x=160, y=200, w=40, h=40))

    detections = find_motion(prev, curr, min_area_px=500, crop=None, frame_ts=12345.678)
    assert detections, "expected at least one detection"
    assert all(d.frame_ts == 12345.678 for d in detections)
