import datetime as dt
from pathlib import Path

import pytest

from curbcam.storage import Database
from curbcam.storage.models import Base
from curbcam.storage.repositories import EventRepo


@pytest.fixture
def repo(tmp_path: Path) -> EventRepo:
    db = Database.for_sqlite_path(tmp_path / "r.sqlite")
    Base.metadata.create_all(db.engine)
    r = EventRepo(db)
    # Six events on 2026-05-28, speeds 20..45, hours 8,8,9,9,10,10.
    for i, (hour, speed, direction) in enumerate(
        [
            (8, 20.0, "L2R"),
            (8, 25.0, "R2L"),
            (9, 30.0, "L2R"),
            (9, 35.0, "R2L"),
            (10, 40.0, "L2R"),
            (10, 45.0, "R2L"),
        ]
    ):
        r.save(
            ts_utc=dt.datetime(2026, 5, 28, hour, i, 0),
            speed_kph=speed,
            direction=direction,
            frame_count=10,
            track_len_px=200,
            image_path=f"e_{i}.jpg",
            thumb_path=f"t_{i}.jpg",
            calibration_id=None,
        )
    return r


def test_summary_percentiles(repo: EventRepo) -> None:
    s = repo.summary(None)
    assert s.count == 6
    assert s.median_kph == pytest.approx(32.5)  # interp between 30 and 35
    assert s.p85_kph == pytest.approx(41.25)  # interp 40..45 at 0.85
    assert s.max_kph == pytest.approx(45.0)


def test_summary_empty_window(repo: EventRepo) -> None:
    s = repo.summary(dt.datetime(2030, 1, 1))
    assert s.count == 0 and s.median_kph == 0.0 and s.max_kph == 0.0


def test_speed_histogram_buckets(repo: EventRepo) -> None:
    # 10-kph bins -> {20:2 (20,25), 30:2 (30,35), 40:2 (40,45)}
    assert repo.speed_histogram(None, 10.0) == {20: 2, 30: 2, 40: 2}


def test_by_hour_returns_24_slots(repo: EventRepo) -> None:
    by_hour = repo.by_hour(None)
    assert len(by_hour) == 24
    assert by_hour[8] == 2 and by_hour[9] == 2 and by_hour[10] == 2
    assert by_hour[0] == 0


def test_daily_counts(repo: EventRepo) -> None:
    assert repo.daily_counts(None) == [("2026-05-28", 6)]


def test_by_direction(repo: EventRepo) -> None:
    bd = repo.by_direction(None)
    assert bd["L2R"][0] == 3 and bd["R2L"][0] == 3  # counts
    assert bd["L2R"][1] == pytest.approx(30.0)  # median of 20,30,40
    assert bd["R2L"][1] == pytest.approx(35.0)  # median of 25,35,45
