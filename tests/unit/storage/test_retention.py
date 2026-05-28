import datetime as dt
from pathlib import Path

import pytest

from curbcam.storage import Database
from curbcam.storage.models import Base, Event
from curbcam.storage.retention import RetentionSweeper


@pytest.fixture
def populated(tmp_path: Path) -> tuple[Database, Path]:
    db = Database.for_sqlite_path(tmp_path / "r.sqlite")
    Base.metadata.create_all(db.engine)
    media = tmp_path / "media"
    media.mkdir()
    # Seed 5 events with associated files.
    with db.session() as s:
        for i in range(5):
            rel = f"events/2026/05/28/event_{i}.jpg"
            (media / rel).parent.mkdir(parents=True, exist_ok=True)
            (media / rel).write_bytes(b"x" * 100_000)   # 100 KB
            s.add(
                Event(
                    ts_utc=dt.datetime(2026, 5, 28, 12, i, 0),
                    speed_kph=30.0,
                    direction="L2R",
                    frame_count=10,
                    track_len_px=200,
                    image_path=rel,
                    thumb_path=rel.replace("events/", "thumbs/"),
                    calibration_id=None,
                )
            )
        s.commit()
    return db, media


def test_sweeper_enforces_max_events_per_day(populated: tuple[Database, Path]) -> None:
    db, media = populated
    sweeper = RetentionSweeper(db=db, media_root=media,
                               max_events_per_day=2, max_total_disk_mb=10_000)
    deleted = sweeper.sweep()
    assert deleted >= 3
    with db.session() as s:
        remaining = s.query(Event).count()
        assert remaining == 2


def test_sweeper_enforces_max_total_disk(populated: tuple[Database, Path]) -> None:
    db, media = populated
    # 5 files x 100 KB = 500 KB ~= 0.5 MB; cap at 0 MB to force purge.
    sweeper = RetentionSweeper(db=db, media_root=media,
                               max_events_per_day=10_000, max_total_disk_mb=0)
    deleted = sweeper.sweep()
    assert deleted >= 1
