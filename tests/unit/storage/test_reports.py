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


def test_speed_dirs_since_returns_speed_direction_pairs(repo: EventRepo) -> None:
    # One scan feeds summary / histogram / by-direction in the reports view-model.
    pairs = repo.speed_dirs_since(None)
    assert len(pairs) == 6
    assert sorted(sp for sp, _ in pairs) == [20.0, 25.0, 30.0, 35.0, 40.0, 45.0]
    assert sorted(sp for sp, d in pairs if d == "R2L") == [25.0, 35.0, 45.0]
    assert repo.speed_dirs_since(dt.datetime(2030, 1, 1)) == []


def test_by_hour_returns_24_slots(repo: EventRepo) -> None:
    by_hour = repo.by_hour(None)  # default UTC
    assert len(by_hour) == 24
    assert by_hour[8] == 2 and by_hour[9] == 2 and by_hour[10] == 2
    assert by_hour[0] == 0


def test_by_hour_buckets_by_local_timezone(tmp_path: Path) -> None:
    # Same 8/9/10 UTC events, but in Los Angeles (UTC-7 in summer) they fall in
    # local hours 1/2/3 — proving the bucket uses the supplied zone, not UTC.
    from zoneinfo import ZoneInfo

    db = Database.for_sqlite_path(tmp_path / "tz.sqlite")
    Base.metadata.create_all(db.engine)
    r = EventRepo(db)
    for i, hour in enumerate((8, 9, 10)):
        r.save(
            ts_utc=dt.datetime(2026, 5, 28, hour, 0, 0),
            speed_kph=30.0,
            direction="L2R",
            frame_count=10,
            track_len_px=100,
            image_path=f"e_{i}.jpg",
            thumb_path=f"t_{i}.jpg",
            calibration_id=None,
        )
    by_hour = r.by_hour(None, ZoneInfo("America/Los_Angeles"))
    assert by_hour[1] == 1 and by_hour[2] == 1 and by_hour[3] == 1
    assert by_hour[8] == 0  # the UTC hour is no longer where the event lands


def test_daily_counts(repo: EventRepo) -> None:
    assert repo.daily_counts(None) == [("2026-05-28", 6)]
