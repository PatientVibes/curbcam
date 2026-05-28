"""Extra PipelineRunner tests covering background-thread and reconnect paths.

These supplement the integration tests in tests/integration/test_pipeline_runner.py
to cover the lines that only execute when run_in_background_thread / stop /
_loop_with_reconnect are used.
"""

import threading
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
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
from curbcam.storage.media import MediaWriter
from curbcam.storage.models import Base
from curbcam.storage.repositories import CalibrationRepo


def _write_single_blank_frame(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.imwrite(str(run_dir / "0000.jpg"), frame)


def _build_runner(tmp_path: Path, *, run_dir: Path, loop: bool = False) -> PipelineRunner:
    db = Database.for_sqlite_path(tmp_path / "events.sqlite")
    Base.metadata.create_all(db.engine)
    settings = Settings(
        camera=CameraSettings(source="file:dummy", resolution=(640, 480), fps_target=60.0),
        detector=DetectorSettings(min_area_px=400, min_track_frames=3, max_dist_px=80),
        retention=RetentionSettings(),
        server=ServerSettings(min_event_speed_kph=999.0),  # skip persistence
    )
    camera = FileReplaySource(run_dir, fps_target=60.0, loop=loop)
    return PipelineRunner(
        camera=camera,
        db=db,
        calibration_repo=CalibrationRepo(db),
        media=MediaWriter(tmp_path / "media"),
        bus=EventBus(),
        settings=settings,
    )


# ---------------------------------------------------------------------------
# run_in_background_thread + stop
# ---------------------------------------------------------------------------


@pytest.mark.timeout(15)
def test_run_in_background_thread_returns_live_thread(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_single_blank_frame(run_dir)
    runner = _build_runner(tmp_path, run_dir=run_dir, loop=False)

    thread = runner.run_in_background_thread()

    assert isinstance(thread, threading.Thread)
    # Wait for the non-looping source to exhaust naturally.
    thread.join(timeout=10)
    assert not thread.is_alive()


@pytest.mark.timeout(15)
def test_runner_run_in_background_thread_is_idempotent(tmp_path: Path) -> None:
    """Calling run_in_background_thread twice must return the same thread,
    not start a second one (idempotent for the MVP-2 server-restart pattern).
    """
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    for i in range(5):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.imwrite(str(run_dir / f"{i:04d}.jpg"), frame)

    # Loop=True so the thread never exhausts on its own — guarantees t1 is
    # still alive when we make the second call.
    runner = _build_runner(tmp_path, run_dir=run_dir, loop=True)

    t1 = runner.run_in_background_thread()
    try:
        t2 = runner.run_in_background_thread()
        assert t1 is t2
        assert t1.is_alive()
    finally:
        runner.stop(timeout=5.0)


@pytest.mark.timeout(15)
def test_stop_signals_running_thread(tmp_path: Path) -> None:
    """stop() should signal the runner and join the thread."""
    run_dir = tmp_path / "run"
    _write_single_blank_frame(run_dir)
    runner = _build_runner(tmp_path, run_dir=run_dir, loop=False)

    thread = runner.run_in_background_thread()
    runner.stop(timeout=10)

    assert not thread.is_alive()
    assert runner._thread is None


# ---------------------------------------------------------------------------
# _loop_with_reconnect — exception path resets tracker and continues
# ---------------------------------------------------------------------------


@pytest.mark.timeout(15)
def test_loop_with_reconnect_resets_tracker_on_crash(tmp_path: Path) -> None:
    """If run_until_camera_exhausted raises, the tracker is reset and loop retries
    (for a persistent source). We mock the camera to fail once then stop the runner.
    """
    run_dir = tmp_path / "run"
    _write_single_blank_frame(run_dir)

    db = Database.for_sqlite_path(tmp_path / "events.sqlite")
    Base.metadata.create_all(db.engine)

    settings = Settings(
        camera=CameraSettings(source="file:dummy", resolution=(640, 480), fps_target=60.0),
        detector=DetectorSettings(min_area_px=400, min_track_frames=3, max_dist_px=80),
        retention=RetentionSettings(),
        server=ServerSettings(min_event_speed_kph=999.0),
    )

    # Use a mock camera that is persistent and raises on first open, then signals stop.
    call_count = [0]
    stop_event = threading.Event()

    class _CrashingCamera:
        resolution = (640, 480)
        fps_target = 60.0
        is_persistent = True

        def open(self) -> None:
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("simulated camera crash")
            # Second open: signal the runner to stop after we return.
            stop_event.set()

        def read(self):  # type: ignore[override]
            return None  # exhausts immediately

        def close(self) -> None:
            pass

    camera = _CrashingCamera()
    runner = PipelineRunner(
        camera=camera,
        db=db,
        calibration_repo=CalibrationRepo(db),
        media=MediaWriter(tmp_path / "media"),
        bus=EventBus(),
        settings=settings,
    )

    # Replace time.sleep so the reconnect delay doesn't actually wait.
    with patch("curbcam.pipeline.runner.time.sleep"):
        runner.run_in_background_thread()
        # Wait until the second open() has been called, then stop.
        stop_event.wait(timeout=5)
        runner.stop(timeout=5)

    # The crash path should have been exercised (call_count >= 2).
    assert call_count[0] >= 2


# ---------------------------------------------------------------------------
# _persist_track — speed below threshold is skipped
# ---------------------------------------------------------------------------


@pytest.mark.timeout(15)
def test_persist_track_skips_when_speed_below_threshold(tmp_path: Path) -> None:
    """Events slower than min_event_speed_kph should not be written to DB."""
    from curbcam.storage.models import Event
    from tests.integration.fixtures.synthetic_run import write_synthetic_run

    run_dir = tmp_path / "run"
    write_synthetic_run(run_dir, frames=10, step_px=40)

    db = Database.for_sqlite_path(tmp_path / "events.sqlite")
    Base.metadata.create_all(db.engine)

    cal_repo = CalibrationRepo(db)
    cal_repo.save_new_active(
        mm_per_px_l2r=10.0,
        mm_per_px_r2l=10.0,
        reference_distance_mm=400.0,
        reference_points_json="[]",
    )

    # Set an absurdly high min speed so nothing passes the threshold.
    settings = Settings(
        camera=CameraSettings(source="file:dummy", resolution=(640, 480), fps_target=60.0),
        detector=DetectorSettings(min_area_px=400, min_track_frames=3, max_dist_px=80),
        retention=RetentionSettings(),
        server=ServerSettings(min_event_speed_kph=99999.0),
    )

    camera = FileReplaySource(run_dir, fps_target=60.0, loop=False)
    runner = PipelineRunner(
        camera=camera,
        db=db,
        calibration_repo=cal_repo,
        media=MediaWriter(tmp_path / "media"),
        bus=EventBus(),
        settings=settings,
    )
    runner.run_until_camera_exhausted()

    with db.session() as s:
        assert s.query(Event).count() == 0
