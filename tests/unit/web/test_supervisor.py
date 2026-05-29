"""Supervisor lifecycle + restart-serialization tests.

These avoid real cameras by patching the runner factory with a fake that
records start/stop calls and simulates a slow rebuild.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from curbcam.config.store import ConfigStore
from curbcam.pipeline.events import EventBus
from curbcam.storage.db import Database, ensure_schema
from curbcam.web.supervisor import Supervisor


class _FakeRunner:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    def run_in_background_thread(self):  # type: ignore[no-untyped-def]
        self.started += 1
        time.sleep(0.05)  # simulate a slow rebuild/start
        # Return a real (un-started) Thread so callers that .join() won't break.
        return threading.Thread(target=lambda: None)

    def stop(self, timeout: float = 5.0) -> None:
        self.stopped += 1


def _make_supervisor(tmp_path: Path) -> Supervisor:
    db = Database.for_sqlite_path(tmp_path / "s.sqlite")
    ensure_schema(db)
    store = ConfigStore(tmp_path / "curbcam.yaml")
    store.load()  # create defaults file
    return Supervisor(
        config_store=store, db=db, bus=EventBus(), media_root=tmp_path / "media"
    )


def test_start_then_stop_builds_and_tears_down_one_runner(tmp_path: Path) -> None:
    sup = _make_supervisor(tmp_path)
    fakes: list[_FakeRunner] = []
    sup._build_runner = lambda settings: fakes.append(_FakeRunner()) or fakes[-1]  # type: ignore[assignment,method-assign]

    sup.start()
    assert len(fakes) == 1 and fakes[0].started == 1
    sup.stop()
    assert fakes[0].stopped == 1


def test_concurrent_restarts_are_serialized(tmp_path: Path) -> None:
    """Two restarts firing at once must not interleave start/stop."""
    sup = _make_supervisor(tmp_path)
    fakes: list[_FakeRunner] = []
    sup._build_runner = lambda settings: fakes.append(_FakeRunner()) or fakes[-1]  # type: ignore[assignment,method-assign]
    sup.start()

    barrier = threading.Barrier(2)

    def fire() -> None:
        barrier.wait()
        sup.restart()

    t1 = threading.Thread(target=fire)
    t2 = threading.Thread(target=fire)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # 1 start + 2 restarts = 3 runners built; each prior runner stopped exactly once.
    assert len(fakes) == 3
    # No runner was stopped more than once (would indicate interleaving).
    assert all(f.stopped <= 1 for f in fakes)
    # The currently-live runner is the last one and was never stopped.
    assert fakes[-1].stopped == 0
