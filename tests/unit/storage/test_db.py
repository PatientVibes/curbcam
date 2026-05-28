# tests/unit/storage/test_db.py
import datetime as dt
from pathlib import Path

import pytest
from sqlalchemy import exc as sa_exc

from curbcam.storage import Calibration, Database, Event
from curbcam.storage.models import Base


def test_database_creates_tables_and_round_trips_an_event(tmp_path: Path) -> None:
    db = Database.for_sqlite_path(tmp_path / "test.sqlite")
    Base.metadata.create_all(db.engine)

    with db.session() as s:
        cal = Calibration(
            created_utc=dt.datetime(2026, 5, 28, 12, 0, 0),
            mm_per_px_l2r=41.3,
            mm_per_px_r2l=41.5,
            reference_distance_mm=4700.0,
            reference_points_json='{"a": [10, 20], "b": [247, 22]}',
            active=True,
            notes=None,
        )
        s.add(cal)
        s.flush()
        event = Event(
            ts_utc=dt.datetime(2026, 5, 28, 12, 0, 5),
            speed_kph=42.7,
            direction="L2R",
            frame_count=12,
            track_len_px=237,
            image_path="events/2026/05/28/event_1.jpg",
            thumb_path="thumbs/2026/05/28/event_1.jpg",
            calibration_id=cal.id,
        )
        s.add(event)
        s.commit()

    with db.session() as s:
        events = s.query(Event).all()
        assert len(events) == 1
        assert abs(float(events[0].speed_kph) - 42.7) < 1e-6


def test_wal_journaling_is_enabled(tmp_path: Path) -> None:
    db = Database.for_sqlite_path(tmp_path / "wal.sqlite")
    with db.engine.connect() as conn:
        mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
        assert mode == "wal"


def test_wal_journaling_persists_across_connections(tmp_path: Path) -> None:
    """A fresh Database wrapper on the same file must still see WAL active."""
    path = tmp_path / "wal-persist.sqlite"
    Database.for_sqlite_path(path)  # first connect sets PRAGMA
    db = Database.for_sqlite_path(path)
    with db.engine.connect() as conn:
        mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
        assert mode == "wal"


def test_unique_active_calibration_constraint_enforced_at_db_layer(
    tmp_path: Path,
) -> None:
    """Defense in depth: even bypassing the repo, the partial unique index fires."""
    db = Database.for_sqlite_path(tmp_path / "constraint.sqlite")
    Base.metadata.create_all(db.engine)
    with db.session() as s:
        s.add(
            Calibration(
                created_utc=dt.datetime(2026, 5, 28, 12, 0, 0),
                mm_per_px_l2r=40.0,
                mm_per_px_r2l=40.0,
                reference_distance_mm=4000.0,
                reference_points_json="[]",
                active=True,
                notes=None,
            )
        )
        s.commit()
    with db.session() as s:
        s.add(
            Calibration(
                created_utc=dt.datetime(2026, 5, 28, 12, 1, 0),
                mm_per_px_l2r=41.0,
                mm_per_px_r2l=41.0,
                reference_distance_mm=4100.0,
                reference_points_json="[]",
                active=True,
                notes=None,
            )
        )
        with pytest.raises(sa_exc.IntegrityError):
            s.commit()


def test_ensure_schema_creates_tables_and_stamps_alembic_version(
    tmp_path: Path,
) -> None:
    """Bootstrap path must leave the DB ready for future `alembic upgrade head`."""
    from curbcam.storage.db import LATEST_MIGRATION_REVISION, Database, ensure_schema

    db = Database.for_sqlite_path(tmp_path / "stamped.sqlite")
    ensure_schema(db)

    with db.engine.connect() as conn:
        # Tables exist
        tables = {
            r[0]
            for r in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "events" in tables
        assert "calibrations" in tables
        assert "alembic_version" in tables

        # Stamped to the latest revision
        row = conn.exec_driver_sql("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
        assert row is not None
        assert row[0] == LATEST_MIGRATION_REVISION


def test_ensure_schema_is_idempotent(tmp_path: Path) -> None:
    """Calling ensure_schema twice must not duplicate the alembic_version row."""
    from curbcam.storage.db import Database, ensure_schema

    db = Database.for_sqlite_path(tmp_path / "stamped.sqlite")
    ensure_schema(db)
    ensure_schema(db)  # second call must not raise or duplicate

    with db.engine.connect() as conn:
        count = conn.exec_driver_sql("SELECT COUNT(*) FROM alembic_version").fetchone()[0]
        assert count == 1
