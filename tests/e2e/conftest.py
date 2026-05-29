"""A real uvicorn server in a background thread for browser tests."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np
import pytest
import uvicorn

from curbcam.config.store import ConfigStore
from curbcam.pipeline.events import EventBus
from curbcam.storage.db import Database, ensure_schema
from curbcam.web.app import create_app
from curbcam.web.auth import AuthStore
from curbcam.web.supervisor import Supervisor


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Server(uvicorn.Server):
    def install_signal_handlers(self) -> None:  # don't hijack the test process
        pass


@pytest.fixture
def live_server(tmp_path: Path) -> Iterator[tuple[str, Supervisor]]:
    frames = tmp_path / "frames"
    frames.mkdir()
    for i in range(8):
        f = np.zeros((480, 640, 3), dtype=np.uint8)
        f[200:240, 100 + i * 40 : 140 + i * 40] = 255
        cv2.imwrite(str(frames / f"f_{i:03d}.jpg"), f)

    db = Database.for_sqlite_path(tmp_path / "db.sqlite")
    ensure_schema(db)
    store = ConfigStore(tmp_path / "curbcam.yaml")
    s = store.load()
    s = s.model_copy(
        update={
            "camera": s.camera.model_copy(
                update={"source": f"file:{frames}", "resolution": (640, 480)}
            )
        }
    )
    store.save(s)
    auth = AuthStore(tmp_path / "auth.json")
    auth.set_password("pw")

    sup = Supervisor(
        config_store=store, db=db, bus=EventBus(), media_root=tmp_path / "media", auth_store=auth
    )
    app = create_app(sup)
    port = _free_port()
    server = _Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}", sup
    finally:
        server.should_exit = True
        th.join(timeout=5)
