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


def test_speeds_since_is_sorted_kph(repo: EventRepo) -> None:
    # Histogram bucketing moved to the display layer; the repo exposes the
    # raw sorted speeds it buckets from.
    assert repo.speeds_since(None) == [20.0, 25.0, 30.0, 35.0, 40.0, 45.0]
    assert repo.speeds_since(None, "R2L") == [25.0, 35.0, 45.0]


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


def test_by_direction(repo: EventRepo) -> None:
    bd = repo.by_direction(None)
    assert bd["L2R"][0] == 3 and bd["R2L"][0] == 3  # counts
    assert bd["L2R"][1] == pytest.approx(30.0)  # median of 20,30,40
    assert bd["R2L"][1] == pytest.approx(35.0)  # median of 25,35,45
