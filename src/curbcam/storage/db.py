"""Thin wrapper around SQLAlchemy engine + session factory.

Enables SQLite WAL journaling at first connection so the writer (detector
thread) and readers (web server, in MVP-2) never block each other.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


class Database:
    def __init__(self, url: str) -> None:
        self._engine: Engine = create_engine(url)
        _enable_sqlite_wal(self._engine)
        self._sessionmaker = sessionmaker(bind=self._engine, expire_on_commit=False)

    @classmethod
    def for_sqlite_path(cls, path: Path) -> Database:
        path.parent.mkdir(parents=True, exist_ok=True)
        return cls(f"sqlite:///{path}")

    @property
    def engine(self) -> Engine:
        return self._engine

    def session(self) -> Session:
        return self._sessionmaker()


# Latest Alembic revision — must be kept in sync with the most recent file
# under migrations/versions/. The CLI uses this to stamp the alembic_version
# table when bootstrapping a fresh database via Base.metadata.create_all,
# so a subsequent `alembic upgrade head` doesn't try to re-create existing
# tables. When a new migration lands, update this constant.
LATEST_MIGRATION_REVISION = "a2a3378804ff"


def ensure_schema(db: Database) -> None:
    """Create all tables and stamp the alembic version.

    Bootstrap helper for the CLI. Alembic-managed in production deploys.
    Idempotent — safe to call repeatedly.
    """
    from curbcam.storage.models import Base

    Base.metadata.create_all(db.engine)
    with db.engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS alembic_version "
            "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        )
        existing = conn.exec_driver_sql(
            "SELECT version_num FROM alembic_version LIMIT 1"
        ).fetchone()
        if existing is None:
            conn.exec_driver_sql(
                f"INSERT INTO alembic_version (version_num) VALUES ('{LATEST_MIGRATION_REVISION}')"
            )


def _enable_sqlite_wal(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()
