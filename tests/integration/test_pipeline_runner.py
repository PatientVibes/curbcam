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
from curbcam.storage.media import MediaWriter
from curbcam.storage.models import Base
from curbcam.storage.repositories import CalibrationRepo, EventRepo
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
