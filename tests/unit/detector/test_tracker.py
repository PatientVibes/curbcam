from curbcam.detector.tracker import Tracker
from curbcam.detector.types import Detection


def det(cx: int, ts: float, area: int = 1000) -> Detection:
    """A simple Detection at (cx, 100) with a 20x20 bbox."""
    return Detection(bbox=(cx - 10, 90, 20, 20), centroid=(cx, 100), area_px=area, frame_ts=ts)


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
    completed = t.update([])  # object gone → track finalised

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
    t.update([det(500, 0.1)])  # >30px away → new track started
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


def test_tracker_flush_finalises_remaining_tracks_and_clears_state() -> None:
    """flush() must return live tracks above min_track_frames and reset state."""
    t = Tracker(max_dist_px=50, min_track_frames=2)
    t.update([det(100, 0.0)])
    t.update([det(120, 0.1)])
    t.update([det(140, 0.2)])

    out = t.flush()
    assert len(out) == 1
    assert len(out[0].detections) == 3
    assert out[0].direction == "L2R"

    # Subsequent flush is a no-op.
    assert t.flush() == []
