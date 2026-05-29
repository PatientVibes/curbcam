from pathlib import Path

import cv2
import numpy as np

from curbcam.camera.file_replay import FileReplaySource
from curbcam.config.schema import Settings
from curbcam.pipeline.events import EventBus
from curbcam.pipeline.runner import PipelineRunner
from curbcam.storage.db import Database, ensure_schema
from curbcam.storage.media import MediaWriter
from curbcam.storage.repositories import CalibrationRepo


def _frames(dirpath: Path, n: int = 8) -> None:
    dirpath.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        x = 100 + i * 40
        frame[200:240, x : x + 40] = 255
        cv2.imwrite(str(dirpath / f"frame_{i:03d}.jpg"), frame)


def _runner(tmp_path: Path) -> PipelineRunner:
    fdir = tmp_path / "frames"
    _frames(fdir)
    db = Database.for_sqlite_path(tmp_path / "db.sqlite")
    ensure_schema(db)
    cam = FileReplaySource(fdir, fps_target=15.0, loop=False)
    return PipelineRunner(
        camera=cam,
        db=db,
        calibration_repo=CalibrationRepo(db),
        media=MediaWriter(tmp_path / "media"),
        bus=EventBus(),
        settings=Settings(),
    )


def test_no_annotated_jpeg_without_viewers(tmp_path: Path) -> None:
    r = _runner(tmp_path)
    r.run_until_camera_exhausted()
    assert r.latest_annotated() is None


def test_annotated_jpeg_present_with_viewer(tmp_path: Path) -> None:
    r = _runner(tmp_path)
    r.add_viewer()
    r.run_until_camera_exhausted()
    jpeg = r.latest_annotated()
    assert jpeg is not None and jpeg[:2] == b"\xff\xd8"  # JPEG SOI marker


def test_capture_still_works_without_viewers(tmp_path: Path) -> None:
    r = _runner(tmp_path)
    r.run_until_camera_exhausted()
    got = r.capture_still()
    assert got is not None
    jpeg, w, h = got
    assert jpeg[:2] == b"\xff\xd8" and (w, h) == (640, 480)


def test_stats_report_fps_after_run(tmp_path: Path) -> None:
    r = _runner(tmp_path)
    r.run_until_camera_exhausted()
    s = r.stats()
    assert s["fps"] >= 0.0 and "tracking" in s and "viewers" in s


def test_preview_encode_is_rate_limited(tmp_path: Path) -> None:
    # With a viewer connected, frames arriving faster than the encode interval
    # must NOT each trigger a JPEG encode (Codex P2: don't encode at camera fps).
    r = _runner(tmp_path)
    r.add_viewer()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    r._tap_frame(frame, 0.0)  # first frame always encodes
    assert r._last_encode_mono == 0.0
    r._tap_frame(frame, 0.05)  # within 0.1s window -> skipped
    assert r._last_encode_mono == 0.0
    r._tap_frame(frame, 0.2)  # >=0.1s since last encode -> encodes
    assert r._last_encode_mono == 0.2
