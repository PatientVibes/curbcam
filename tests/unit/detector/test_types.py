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
