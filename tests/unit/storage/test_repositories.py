import datetime as dt
from pathlib import Path

import pytest

from curbcam.storage import Calibration, Database
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
