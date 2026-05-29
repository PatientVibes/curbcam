import datetime as dt
from pathlib import Path

import pytest

from curbcam.storage import Database
from curbcam.storage.models import Base
from curbcam.storage.repositories import EventFilter, EventRepo


@pytest.fixture
def repo(tmp_path: Path) -> EventRepo:
    db = Database.for_sqlite_path(tmp_path / "q.sqlite")
    Base.metadata.create_all(db.engine)
    r = EventRepo(db)
    for i in range(6):
        r.save(
            ts_utc=dt.datetime(2026, 5, 28, 12, i, 0),
            speed_kph=20.0 + i * 5,           # 20,25,30,35,40,45
            direction="L2R" if i % 2 == 0 else "R2L",
            frame_count=10,
            track_len_px=200,
            image_path=f"events/e_{i}.jpg",
            thumb_path=f"thumbs/e_{i}.jpg",
            calibration_id=None,
        )
    return r


def test_query_filters_by_direction(repo: EventRepo) -> None:
    rows = repo.query(EventFilter(direction="R2L"))
    assert {r.direction for r in rows} == {"R2L"}
    assert len(rows) == 3


def test_query_filters_by_speed_range(repo: EventRepo) -> None:
    rows = repo.query(EventFilter(min_speed_kph=30.0, max_speed_kph=40.0))
    assert sorted(r.speed_kph for r in rows) == [30.0, 35.0, 40.0]


def test_query_orders_newest_first_and_paginates_by_cursor(repo: EventRepo) -> None:
    page1 = repo.query(EventFilter(), limit=2)
    assert [r.speed_kph for r in page1] == [45.0, 40.0]  # newest ts first
    cursor = (page1[-1].ts_utc, page1[-1].id)
    page2 = repo.query(EventFilter(), cursor=cursor, limit=2)
    assert [r.speed_kph for r in page2] == [35.0, 30.0]


def test_delete_older_than_returns_media_paths(repo: EventRepo) -> None:
    paths = repo.delete_older_than(dt.datetime(2026, 5, 28, 12, 3, 0))
    # 3 rows deleted (minutes 0,1,2), each with image + thumb -> 6 paths.
    assert len(paths) == 6
    assert all(p.startswith(("events/", "thumbs/")) for p in paths)
    assert len(repo.query(EventFilter())) == 3
