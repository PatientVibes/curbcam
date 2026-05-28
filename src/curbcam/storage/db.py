"""Thin wrapper around SQLAlchemy engine + session factory.

Enables SQLite WAL journaling at first connection so the writer (detector
thread) and readers (web server, in MVP-2) never block each other.
"""

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


class Database:
    def __init__(self, url: str) -> None:
        self._engine: Engine = create_engine(url, future=True)
        _enable_sqlite_wal(self._engine)
        self._sessionmaker = sessionmaker(bind=self._engine, expire_on_commit=False)

    @classmethod
    def for_sqlite_path(cls, path: Path) -> "Database":
        path.parent.mkdir(parents=True, exist_ok=True)
        return cls(f"sqlite:///{path}")

    @property
    def engine(self) -> Engine:
        return self._engine

    def session(self) -> Session:
        return self._sessionmaker()


def _enable_sqlite_wal(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()
