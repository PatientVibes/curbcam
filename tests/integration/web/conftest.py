"""A FileReplaySource-backed app + TestClient, no hardware needed."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from curbcam.config.store import ConfigStore
from curbcam.pipeline.events import EventBus
from curbcam.storage.db import Database, ensure_schema
from curbcam.web.app import create_app
from curbcam.web.supervisor import Supervisor


def _write_frames(dirpath: Path, n: int = 8) -> None:
    """STATIC frames on purpose: identical frames produce no motion, so the
    running pipeline never persists events of its own. Integration tests that
    assert event counts seed events explicitly via supervisor.events.save —
    a moving fixture here would pollute those counts once a calibration is
    active. The frame still exists, so live-preview/capture_still work.
    """
    dirpath.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[200:240, 300:340] = 255  # same position in every frame -> no motion
        cv2.imwrite(str(dirpath / f"frame_{i:03d}.jpg"), frame)


@pytest.fixture
def supervisor(tmp_path: Path) -> Supervisor:
    frames = tmp_path / "frames"
    _write_frames(frames)
    db = Database.for_sqlite_path(tmp_path / "curbcam.sqlite")
    ensure_schema(db)
    store = ConfigStore(tmp_path / "curbcam.yaml")
    settings = store.load()
    settings = settings.model_copy(
        update={"camera": settings.camera.model_copy(update={"source": f"file:{frames}"})}
    )
    store.save(settings)
    return Supervisor(
        config_store=store, db=db, bus=EventBus(), media_root=tmp_path / "media"
    )


@pytest.fixture
def client(supervisor: Supervisor) -> Iterator[TestClient]:
    app = create_app(supervisor)
    # TestClient runs startup/shutdown (which start/stop the supervisor).
    with TestClient(app) as c:
        yield c
