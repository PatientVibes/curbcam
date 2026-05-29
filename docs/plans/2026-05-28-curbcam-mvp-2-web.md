# curbcam MVP-2 — Web Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `curbcam serve` — a single-process, LAN-only web app that runs the MVP-1 detector pipeline in a background thread and exposes a wizard-driven htmx UI: dashboard, live MJPEG preview, SSE event feed, events history + CSV export, settings, and the first-run/alignment/calibration wizards, all behind a single admin password.

**Architecture:** A new `src/curbcam/web/` package. A `Supervisor` (held in `app.state`) owns the `PipelineRunner` thread, `EventBus`, `Database`, `ConfigStore`, repos, `MediaWriter`, and `AuthStore`; it serializes `start/stop/restart` under a lock. `create_app(supervisor)` is a pure function returning a FastAPI app, so the whole app is testable with a `FileReplaySource`-backed supervisor and no hardware. Server-rendered Jinja2 + vendored htmx; MJPEG reads a single annotated-frame slot at 5 fps; SSE drains a bounded per-client queue off the existing `EventBus`. Settings edits persist to YAML then trigger a graceful pipeline-thread restart.

**Tech Stack:** Python 3.12, FastAPI, uvicorn[standard], Jinja2, python-multipart, itsdangerous, argon2-cffi, htmx (vendored), OpenCV (existing), SQLAlchemy/SQLite (existing), pytest + httpx TestClient, Playwright (one smoke test).

**Reference:** Design spec at `docs/specs/2026-05-28-curbcam-mvp-2-web.md` (cited as §N). Overall design at `docs/specs/2026-05-28-curbcam-design.md`. MVP-1 plan style: `docs/plans/2026-05-28-curbcam-mvp-1-headless-foundation.md`.

---

## Slices (independently shippable groups)

The plan is grouped so each slice leaves the tree green and shippable on its own:

- **Slice A — App foundation & lifecycle** (Tasks 1–3): deps, `Supervisor`, `create_app`, `curbcam serve`.
- **Slice B — Auth** (Tasks 4–6): `AuthStore`, sessions + login/logout, first-run gate.
- **Slice C — Frame tap & live streams** (Tasks 7–11): runner frame tap, bounded `EventBus`, MJPEG, SSE, supervisor stats/`capture_still`.
- **Slice D — Viewing UI** (Tasks 12–16): units, `EventRepo.query`, dashboard, events history, CSV.
- **Slice E — Settings** (Tasks 17–19): settings page, save+restart, stream tokens + data deletion.
- **Slice F — Wizards** (Tasks 20–25): capture, measure, calibration wizard, alignment wizard, first-run flow, Playwright smoke.
- **Slice G — Finalize** (Task 26): lint/type/coverage, README, push + tag.

---

## File Structure

```
src/curbcam/web/
├── __init__.py        # exports create_app, Supervisor
├── app.py             # create_app(supervisor) -> FastAPI; mounts routers/static/media; middleware; startup/shutdown
├── supervisor.py      # Supervisor: owns runner thread + collaborators; start/stop/restart under a lock
├── deps.py            # get_supervisor, require_session, require_stream_auth
├── auth.py            # AuthStore (auth.json), Argon2 hashing, itsdangerous cookie + stream-token signing
├── units.py           # kph<->mph conversion + display formatting
├── streams.py         # mjpeg_generator, sse_generator, no-signal placeholder JPEG
├── routes/
│   ├── __init__.py
│   ├── auth.py        # /api/auth/login, /api/auth/logout
│   ├── pages.py       # /, /events, /settings, /setup, /setup/align, /setup/calibrate
│   ├── events.py      # /api/events, /api/events.csv, /api/events/stream
│   ├── stream.py      # /api/stream.mjpeg
│   ├── settings.py    # /api/settings (+ /api/tokens, /api/events/purge)
│   ├── calibration.py # /api/calibration/capture, /api/calibration/measure
│   ├── crop.py        # /api/crop
│   └── debug.py       # /api/debug/stats
├── templates/         # base.html, dashboard.html, events.html, settings.html, setup/*.html + partials
└── static/            # app.css, app.js, vendor/htmx.min.js, no-signal.jpg
tests/
├── unit/web/          # test_auth.py, test_units.py, test_supervisor.py, test_events_query.py, test_event_bus_bounded.py
└── integration/web/   # test_app.py, test_auth_flow.py, test_gate.py, test_streams.py, test_settings.py,
                       # test_calibration.py, test_crop.py, test_csv.py
tests/e2e/             # test_calibrate_smoke.py (Playwright)
```

**Modified existing files:**
- `pyproject.toml` — add web deps + `playwright` to dev extras.
- `src/curbcam/cli.py` — add `serve` command.
- `src/curbcam/pipeline/runner.py` — add frame tap (annotated slot + full-frame snapshot + viewer/overlay flags + stats), keeping MVP-1 behavior unchanged.
- `src/curbcam/pipeline/events.py` — bounded subscriber queues.
- `src/curbcam/storage/repositories.py` — add `EventRepo.query` + `EventRepo.delete_older_than`.

---

## Slice A — App foundation & lifecycle

### Task 1: Web dependencies + package skeleton + Supervisor

**Files:**
- Modify: `pyproject.toml`
- Create: `src/curbcam/web/__init__.py`
- Create: `src/curbcam/web/supervisor.py`
- Create: `tests/unit/web/__init__.py`
- Create: `tests/unit/web/test_supervisor.py`

- [ ] **Step 1: Add dependencies to `pyproject.toml`**

In `[project].dependencies`, add:

```toml
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "jinja2>=3.1",
    "python-multipart>=0.0.9",
    "itsdangerous>=2.2",
    "argon2-cffi>=23.1",
```

In `[project.optional-dependencies].dev`, add:

```toml
    "playwright>=1.47",
    "httpx>=0.27",
```

Then install:

```bash
cd D:/curbcam
uv pip install -e ".[dev]"
```

Expected: resolves and installs without error.

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/web/test_supervisor.py
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
    t1.start(); t2.start(); t1.join(); t2.join()

    # 1 start + 2 restarts = 3 runners built; each prior runner stopped exactly once.
    assert len(fakes) == 3
    # No runner was stopped more than once (would indicate interleaving).
    assert all(f.stopped <= 1 for f in fakes)
    # The currently-live runner is the last one and was never stopped.
    assert fakes[-1].stopped == 0
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run pytest tests/unit/web/test_supervisor.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'curbcam.web'`.

- [ ] **Step 4: Write `src/curbcam/web/supervisor.py`**

```python
"""Owns all long-lived web-process state and the pipeline lifecycle.

A single Supervisor instance is held on app.state. Routes depend only on
it (never on globals). start/stop/restart are serialized by a lock so two
near-simultaneous settings saves cannot race to replace the runner thread
(spec §4 concurrency invariant). The live-frame tap (latest_frame /
capture_still / viewers / overlay / stats) is wired in Slice C once the
PipelineRunner exposes it; until then those return safe defaults.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from curbcam.camera.factory import camera_from_source
from curbcam.config.store import ConfigStore
from curbcam.pipeline.events import EventBus, EventEnvelope
from curbcam.pipeline.runner import PipelineRunner
from curbcam.storage.db import Database
from curbcam.storage.media import MediaWriter
from curbcam.storage.repositories import CalibrationRepo, EventRepo


class Supervisor:
    def __init__(
        self,
        *,
        config_store: ConfigStore,
        db: Database,
        bus: EventBus,
        media_root: Path,
    ) -> None:
        self._config_store = config_store
        self._db = db
        self._bus = bus
        self._media_root = media_root
        self._media = MediaWriter(media_root)
        self.calibrations = CalibrationRepo(db)
        self.events = EventRepo(db)
        self._runner: PipelineRunner | None = None
        self._lock = threading.Lock()
        self._started_at: float | None = None

    # -- exposed collaborators (read-only access for routes) --
    @property
    def bus(self) -> EventBus:
        return self._bus

    @property
    def db(self) -> Database:
        return self._db

    @property
    def config_store(self) -> ConfigStore:
        return self._config_store

    @property
    def media_root(self) -> Path:
        return self._media_root

    # -- lifecycle --
    def _build_runner(self, settings) -> PipelineRunner:  # type: ignore[no-untyped-def]
        cam = camera_from_source(
            settings.camera.source,
            resolution=settings.camera.resolution,
            fps_target=settings.camera.fps_target,
            loop=True,
        )
        return PipelineRunner(
            camera=cam,
            db=self._db,
            calibration_repo=self.calibrations,
            media=self._media,
            bus=self._bus,
            settings=settings,
        )

    def start(self) -> None:
        with self._lock:
            if self._runner is not None:
                return
            settings = self._config_store.load()
            self._runner = self._build_runner(settings)
            self._runner.run_in_background_thread()
            self._started_at = time.monotonic()

    def stop(self) -> None:
        with self._lock:
            if self._runner is not None:
                self._runner.stop()
                self._runner = None

    def restart(self) -> None:
        with self._lock:
            if self._runner is not None:
                self._runner.stop()
            settings = self._config_store.load()
            self._runner = self._build_runner(settings)
            self._runner.run_in_background_thread()
            self._started_at = time.monotonic()
        # Notify connected UIs after releasing the lock.
        self._bus.publish_threadsafe(EventEnvelope(kind="settings_changed", payload={}))

    def stats(self) -> dict:
        uptime = 0.0 if self._started_at is None else time.monotonic() - self._started_at
        return {"uptime_s": round(uptime, 1), "running": self._runner is not None}
```

- [ ] **Step 5: Create `tests/unit/web/__init__.py` (empty) and run tests**

```bash
uv run pytest tests/unit/web/test_supervisor.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/curbcam/web/__init__.py src/curbcam/web/supervisor.py tests/unit/web/
git commit -m "feat(web): web deps + Supervisor lifecycle with restart lock"
```

---

### Task 2: create_app + get_supervisor dependency + /api/debug/stats

**Files:**
- Create: `src/curbcam/web/app.py`
- Create: `src/curbcam/web/deps.py`
- Create: `src/curbcam/web/routes/__init__.py`
- Create: `src/curbcam/web/routes/debug.py`
- Modify: `src/curbcam/web/__init__.py`
- Create: `tests/integration/web/__init__.py`
- Create: `tests/integration/web/conftest.py`
- Create: `tests/integration/web/test_app.py`

- [ ] **Step 1: Write the shared integration fixture**

```python
# tests/integration/web/conftest.py
"""A FileReplaySource-backed app + TestClient, no hardware needed."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import numpy as np
import cv2
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
```

- [ ] **Step 2: Write the failing test**

```python
# tests/integration/web/test_app.py
from fastapi.testclient import TestClient


def test_debug_stats_returns_running_true(client: TestClient) -> None:
    resp = client.get("/api/debug/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["running"] is True
    assert "uptime_s" in body
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run pytest tests/integration/web/test_app.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'curbcam.web.app'`.

- [ ] **Step 4: Write `src/curbcam/web/deps.py`**

```python
"""FastAPI dependencies. Auth deps are filled in Slice B."""
from __future__ import annotations

from fastapi import Request

from curbcam.web.supervisor import Supervisor


def get_supervisor(request: Request) -> Supervisor:
    return request.app.state.supervisor  # type: ignore[no-any-return]
```

- [ ] **Step 5: Write `src/curbcam/web/routes/debug.py`**

```python
"""Detector stats for the dashboard pill + diagnostics."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from curbcam.web.deps import get_supervisor
from curbcam.web.supervisor import Supervisor

router = APIRouter()


@router.get("/api/debug/stats")
def debug_stats(sup: Supervisor = Depends(get_supervisor)) -> dict:
    return sup.stats()
```

- [ ] **Step 6: Write `src/curbcam/web/routes/__init__.py` (empty), then `src/curbcam/web/app.py`**

```python
"""Composition root: build the FastAPI app from an injected Supervisor.

Pure function of the Supervisor so the whole app is testable with a
FileReplaySource-backed supervisor (no hardware). Startup binds the event
loop to the bus and starts the pipeline; shutdown stops it.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from curbcam.web.routes import debug
from curbcam.web.supervisor import Supervisor


def create_app(supervisor: Supervisor) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        supervisor.bus.bind_loop(asyncio.get_running_loop())
        supervisor.start()
        try:
            yield
        finally:
            supervisor.stop()

    app = FastAPI(title="curbcam", lifespan=lifespan)
    app.state.supervisor = supervisor
    app.include_router(debug.router)
    return app
```

- [ ] **Step 7: Update `src/curbcam/web/__init__.py`**

```python
"""curbcam web layer: FastAPI app + Supervisor."""
from curbcam.web.app import create_app
from curbcam.web.supervisor import Supervisor

__all__ = ["Supervisor", "create_app"]
```

- [ ] **Step 8: Create `tests/integration/web/__init__.py` (empty) and run**

```bash
uv run pytest tests/integration/web/test_app.py -v
```

Expected: 1 passed.

- [ ] **Step 9: Commit**

```bash
git add src/curbcam/web/ tests/integration/web/
git commit -m "feat(web): create_app composition root + /api/debug/stats"
```

---

### Task 3: `curbcam serve` CLI command

**Files:**
- Modify: `src/curbcam/cli.py`
- Create: `tests/integration/test_cli_serve.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_cli_serve.py
"""serve must construct the app + supervisor and hand off to uvicorn.

We patch uvicorn.run so the test doesn't actually bind a socket.
"""
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import curbcam.cli as cli_mod
from curbcam.cli import app

runner = CliRunner()


def test_serve_builds_app_and_calls_uvicorn(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict = {}

    def fake_run(app_obj, host: str, port: int, **kw) -> None:  # type: ignore[no-untyped-def]
        captured["app"] = app_obj
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr(cli_mod.uvicorn, "run", fake_run)

    result = runner.invoke(
        app,
        [
            "serve",
            "--host", "127.0.0.1",
            "--port", "9111",
            "--config", str(tmp_path / "curbcam.yaml"),
            "--data-dir", str(tmp_path / "data"),
            "--media-dir", str(tmp_path / "media"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9111
    assert captured["app"].__class__.__name__ == "FastAPI"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/integration/test_cli_serve.py -v
```

Expected: FAIL (`serve` is not a command / `uvicorn` not imported in cli).

- [ ] **Step 3: Add the `serve` command to `src/curbcam/cli.py`**

Add `import uvicorn` near the top imports, and the imports:

```python
from curbcam.pipeline.events import EventBus
from curbcam.web.app import create_app
from curbcam.web.supervisor import Supervisor
```

Add this command (after `detect`):

```python
@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind address"),
    port: int = typer.Option(8000, help="Bind port"),
    config: Path = typer.Option(Path("curbcam.yaml"), help="Path to YAML config"),
    data_dir: Path = typer.Option(Path("./data"), help="Directory for SQLite DB"),
    media_dir: Path = typer.Option(Path("./media"), help="Directory for event JPEGs"),
) -> None:
    """Run the web app: detector pipeline + UI in one process."""
    store = ConfigStore(config)
    settings = store.load()
    _setup_logging(settings.server.log_level)

    db = Database.for_sqlite_path(data_dir / "curbcam.sqlite")
    ensure_schema(db)

    supervisor = Supervisor(
        config_store=store, db=db, bus=EventBus(), media_root=media_dir
    )
    app_obj = create_app(supervisor)
    uvicorn.run(app_obj, host=host, port=port)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/integration/test_cli_serve.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/curbcam/cli.py tests/integration/test_cli_serve.py
git commit -m "feat(cli): curbcam serve command"
```

---

## Slice B — Auth

### Task 4: AuthStore (Argon2 + secret key + stream tokens)

**Files:**
- Create: `src/curbcam/web/auth.py`
- Create: `tests/unit/web/test_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/web/test_auth.py
from pathlib import Path

from curbcam.web.auth import AuthStore


def test_no_password_until_set(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.json")
    assert store.has_password() is False


def test_set_and_verify_password(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.json")
    store.set_password("hunter2")
    assert store.has_password() is True
    assert store.verify_password("hunter2") is True
    assert store.verify_password("wrong") is False


def test_password_is_not_stored_plaintext(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    AuthStore(path).set_password("hunter2")
    assert "hunter2" not in path.read_text(encoding="utf-8")


def test_secret_key_is_stable_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    s1 = AuthStore(path)
    s1.set_password("x")
    key1 = s1.secret_key()
    key2 = AuthStore(path).secret_key()
    assert key1 == key2 and len(key1) >= 32


def test_mint_verify_and_revoke_stream_token(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.json")
    store.set_password("x")
    token_id, raw = store.mint_stream_token("Home Assistant")
    assert store.verify_stream_token(raw) is True
    assert any(t["label"] == "Home Assistant" for t in store.list_stream_tokens())
    store.revoke_stream_token(token_id)
    assert store.verify_stream_token(raw) is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/web/test_auth.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'curbcam.web.auth'`.

- [ ] **Step 3: Write `src/curbcam/web/auth.py`**

```python
"""Single-admin auth state persisted to auth.json (spec §6).

Stores: an Argon2 password hash, a stable random secret_key (used by
itsdangerous to sign session cookies and stream tokens), and a list of
revocable stream tokens stored only as Argon2 hashes. Raw tokens are
shown to the user once at mint time.
"""
from __future__ import annotations

import json
import secrets
import uuid
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher()


class AuthStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # -- password --
    def has_password(self) -> bool:
        return bool(self._read().get("password_hash"))

    def set_password(self, password: str) -> None:
        data = self._read()
        data["password_hash"] = _ph.hash(password)
        if not data.get("secret_key"):
            data["secret_key"] = secrets.token_urlsafe(32)
        data.setdefault("stream_tokens", [])
        self._write(data)

    def verify_password(self, password: str) -> bool:
        h = self._read().get("password_hash")
        if not h:
            return False
        try:
            return _ph.verify(h, password)
        except VerifyMismatchError:
            return False

    def secret_key(self) -> str:
        data = self._read()
        key = data.get("secret_key")
        if not key:
            key = secrets.token_urlsafe(32)
            data["secret_key"] = key
            self._write(data)
        return key  # type: ignore[no-any-return]

    # -- stream tokens --
    def mint_stream_token(self, label: str) -> tuple[str, str]:
        raw = secrets.token_urlsafe(24)
        token_id = uuid.uuid4().hex[:8]
        data = self._read()
        tokens = data.setdefault("stream_tokens", [])
        tokens.append({"id": token_id, "label": label, "token_hash": _ph.hash(raw)})
        self._write(data)
        return token_id, raw

    def verify_stream_token(self, raw: str) -> bool:
        for t in self._read().get("stream_tokens", []):
            try:
                if _ph.verify(t["token_hash"], raw):
                    return True
            except VerifyMismatchError:
                continue
        return False

    def list_stream_tokens(self) -> list[dict[str, Any]]:
        return [
            {"id": t["id"], "label": t["label"]}
            for t in self._read().get("stream_tokens", [])
        ]

    def revoke_stream_token(self, token_id: str) -> None:
        data = self._read()
        data["stream_tokens"] = [
            t for t in data.get("stream_tokens", []) if t["id"] != token_id
        ]
        self._write(data)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/web/test_auth.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/curbcam/web/auth.py tests/unit/web/test_auth.py
git commit -m "feat(web): AuthStore — Argon2 password + secret key + stream tokens"
```

---

### Task 5: Sessions + login/logout + require_session

**Files:**
- Modify: `src/curbcam/web/supervisor.py` (own an `AuthStore`)
- Modify: `src/curbcam/web/deps.py` (`require_session`)
- Create: `src/curbcam/web/routes/auth.py`
- Modify: `src/curbcam/web/app.py` (register auth router; build `AuthStore`)
- Modify: `tests/integration/web/conftest.py` (set a password helper)
- Create: `tests/integration/web/test_auth_flow.py`

- [ ] **Step 1: Give the Supervisor an AuthStore**

In `supervisor.py`, add to imports and `__init__`:

```python
from curbcam.web.auth import AuthStore
```

In `__init__` params add `auth_store: AuthStore` and store it:

```python
    def __init__(self, *, config_store, db, bus, media_root, auth_store):  # type: ignore[no-untyped-def]
        ...
        self.auth = auth_store
```

Update the unit-test supervisor factory and the integration `supervisor` fixture to pass `auth_store=AuthStore(tmp_path / "auth.json")`.

- [ ] **Step 2: Write the failing test**

```python
# tests/integration/web/test_auth_flow.py
from fastapi.testclient import TestClient

from curbcam.web.auth import AuthStore


def test_login_rejects_bad_password(client: TestClient, supervisor) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("correct-horse")
    resp = client.post("/api/auth/login", data={"password": "nope"}, follow_redirects=False)
    assert resp.status_code == 401


def test_login_sets_session_cookie(client: TestClient, supervisor) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("correct-horse")
    resp = client.post("/api/auth/login", data={"password": "correct-horse"}, follow_redirects=False)
    assert resp.status_code in (200, 303)
    assert "curbcam_session" in resp.cookies


def test_logout_clears_session(client: TestClient, supervisor) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("correct-horse")
    client.post("/api/auth/login", data={"password": "correct-horse"})
    resp = client.delete("/api/auth/logout")
    assert resp.status_code in (200, 204)
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run pytest tests/integration/web/test_auth_flow.py -v
```

Expected: FAIL (no `/api/auth/login` route).

- [ ] **Step 4: Add session helpers + `require_session` to `src/curbcam/web/deps.py`**

```python
"""FastAPI dependencies + session cookie helpers."""
from __future__ import annotations

from fastapi import HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer

from curbcam.web.supervisor import Supervisor

SESSION_COOKIE = "curbcam_session"
_MAX_AGE_S = 30 * 24 * 3600  # 30-day sliding expiry


def get_supervisor(request: Request) -> Supervisor:
    return request.app.state.supervisor  # type: ignore[no-any-return]


def _serializer(sup: Supervisor) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(sup.auth.secret_key(), salt="curbcam-session")


def issue_session(sup: Supervisor, response: Response) -> None:
    token = _serializer(sup).dumps({"admin": True})
    response.set_cookie(
        SESSION_COOKIE, token, max_age=_MAX_AGE_S, httponly=True, samesite="lax"
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)


def session_is_valid(sup: Supervisor, request: Request) -> bool:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return False
    try:
        _serializer(sup).loads(raw, max_age=_MAX_AGE_S)
        return True
    except BadSignature:
        return False


def require_session(request: Request) -> None:
    sup: Supervisor = request.app.state.supervisor
    if not session_is_valid(sup, request):
        raise HTTPException(status_code=401, detail="Not authenticated")
```

- [ ] **Step 5: Write `src/curbcam/web/routes/auth.py`**

```python
"""Login/logout. /api/auth/login is the only fully public endpoint."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Form, HTTPException, Response

from curbcam.web.deps import clear_session, get_supervisor, issue_session
from curbcam.web.supervisor import Supervisor

router = APIRouter()


@router.post("/api/auth/login")
def login(
    password: str = Form(...),
    sup: Supervisor = Depends(get_supervisor),
) -> Response:
    if not sup.auth.verify_password(password):
        time.sleep(0.25)  # fixed delay blunts brute force (spec §6 threat model)
        raise HTTPException(status_code=401, detail="Invalid password")
    resp = Response(status_code=200)
    issue_session(sup, resp)
    return resp


@router.delete("/api/auth/logout")
def logout() -> Response:
    resp = Response(status_code=204)
    clear_session(resp)
    return resp
```

- [ ] **Step 6: Register the auth router in `src/curbcam/web/app.py`**

Add `from curbcam.web.routes import auth, debug` and `app.include_router(auth.router)`.

- [ ] **Step 7: Run tests**

```bash
uv run pytest tests/integration/web/test_auth_flow.py -v
```

Expected: 3 passed.

- [ ] **Step 8: Commit**

```bash
git add src/curbcam/web/ tests/
git commit -m "feat(web): session cookie auth + login/logout + require_session"
```

---

### Task 6: First-run gate middleware

**Files:**
- Create: `src/curbcam/web/middleware.py`
- Modify: `src/curbcam/web/app.py` (install middleware)
- Create: `tests/integration/web/test_gate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/web/test_gate.py
from fastapi.testclient import TestClient


def test_unconfigured_redirects_to_setup(client: TestClient) -> None:
    # No password set + no active calibration → gate redirects.
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/setup"


def test_setup_and_static_are_exempt(client: TestClient) -> None:
    resp = client.get("/setup", follow_redirects=False)
    assert resp.status_code != 303  # may 200 or 404 (page added later), never redirected


def test_login_endpoint_is_exempt(client: TestClient) -> None:
    resp = client.post("/api/auth/login", data={"password": "x"}, follow_redirects=False)
    # Not redirected by the gate; auth route handles it (401 here, no password yet).
    assert resp.status_code == 401


def test_configured_does_not_redirect(client: TestClient, supervisor) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("x")
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    # Authenticated session present:
    client.post("/api/auth/login", data={"password": "x"})
    resp = client.get("/api/debug/stats", follow_redirects=False)
    assert resp.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/integration/web/test_gate.py -v
```

Expected: FAIL (no redirect; gate not installed).

- [ ] **Step 3: Write `src/curbcam/web/middleware.py`**

```python
"""First-run gate (spec §6).

If no admin password OR no active calibration exists, every route except
the setup/auth/calibration/crop/static surface is 303-redirected to
/setup. The gate only controls redirection; per-route require_session
still enforces authentication on protected endpoints.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

_EXEMPT_PREFIXES = (
    "/setup",
    "/api/auth/login",
    "/api/calibration",
    "/api/crop",
    "/static",
)


def _is_exempt(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") or path.startswith(p) for p in _EXEMPT_PREFIXES)


async def first_run_gate(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    sup = request.app.state.supervisor
    if not _is_exempt(request.url.path):
        configured = sup.auth.has_password() and sup.calibrations.get_active() is not None
        if not configured:
            return RedirectResponse("/setup", status_code=303)
    return await call_next(request)
```

- [ ] **Step 4: Install the middleware in `src/curbcam/web/app.py`**

Add inside `create_app`, after `app.state.supervisor = supervisor`:

```python
    from curbcam.web.middleware import first_run_gate

    app.middleware("http")(first_run_gate)
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/integration/web/test_gate.py -v
```

Expected: 4 passed. (`/setup` returns 404 until Task 24 adds the page — the test only asserts it is not a 303.)

- [ ] **Step 6: Commit**

```bash
git add src/curbcam/web/middleware.py src/curbcam/web/app.py tests/integration/web/test_gate.py
git commit -m "feat(web): first-run gate middleware"
```

---

## Slice C — Frame tap & live streams

### Task 7: PipelineRunner live-frame tap + stats

**Files:**
- Modify: `src/curbcam/pipeline/runner.py`
- Create: `tests/unit/pipeline/test_runner_tap.py`

The tap is **additive** — MVP-1 behavior (event persistence, reconnect) is
unchanged, and with zero viewers no JPEG encoding happens. `capture_still`
reads a lock-protected snapshot of the latest full frame (spec §4) — never a
mid-loop re-entrant grab.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/pipeline/test_runner_tap.py
from pathlib import Path

import cv2
import numpy as np

from curbcam.camera.file_replay import FileReplaySource
from curbcam.config.schema import Settings
from curbcam.pipeline.events import EventBus
from curbcam.pipeline.runner import PipelineRunner
from curbcam.storage.db import Database, ensure_schema
from curbcam.storage.media import MediaWriter
from curbcam.storage.repositories import CalibrationRepo


def _frames(dirpath: Path, n: int = 8) -> None:
    dirpath.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        x = 100 + i * 40
        frame[200:240, x : x + 40] = 255
        cv2.imwrite(str(dirpath / f"frame_{i:03d}.jpg"), frame)


def _runner(tmp_path: Path) -> PipelineRunner:
    fdir = tmp_path / "frames"
    _frames(fdir)
    db = Database.for_sqlite_path(tmp_path / "db.sqlite")
    ensure_schema(db)
    cam = FileReplaySource(fdir, fps_target=15.0, loop=False)
    return PipelineRunner(
        camera=cam,
        db=db,
        calibration_repo=CalibrationRepo(db),
        media=MediaWriter(tmp_path / "media"),
        bus=EventBus(),
        settings=Settings(),
    )


def test_no_annotated_jpeg_without_viewers(tmp_path: Path) -> None:
    r = _runner(tmp_path)
    r.run_until_camera_exhausted()
    assert r.latest_annotated() is None


def test_annotated_jpeg_present_with_viewer(tmp_path: Path) -> None:
    r = _runner(tmp_path)
    r.add_viewer()
    r.run_until_camera_exhausted()
    jpeg = r.latest_annotated()
    assert jpeg is not None and jpeg[:2] == b"\xff\xd8"  # JPEG SOI marker


def test_capture_still_works_without_viewers(tmp_path: Path) -> None:
    r = _runner(tmp_path)
    r.run_until_camera_exhausted()
    got = r.capture_still()
    assert got is not None
    jpeg, w, h = got
    assert jpeg[:2] == b"\xff\xd8" and (w, h) == (640, 480)


def test_stats_report_fps_after_run(tmp_path: Path) -> None:
    r = _runner(tmp_path)
    r.run_until_camera_exhausted()
    s = r.stats()
    assert s["fps"] >= 0.0 and "tracking" in s and "viewers" in s
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/pipeline/test_runner_tap.py -v
```

Expected: FAIL with `AttributeError: 'PipelineRunner' object has no attribute 'add_viewer'`.

- [ ] **Step 3: Add tap state to `PipelineRunner.__init__`**

At the end of `__init__` (after the `self._tracker = Tracker(...)` block), add:

```python
        # -- live preview / stats tap (MVP-2) --
        self._frame_lock = threading.Lock()
        self._latest_annotated_jpeg: bytes | None = None
        self._latest_full_bgr = None  # type: ignore[var-annotated]
        self._last_detections: list = []
        self._viewers = 0
        self._overlay = False
        self._fps_ema = 0.0
        self._last_mono: float | None = None
        self._tracking = False
```

- [ ] **Step 4: Add the public tap API to `PipelineRunner`**

Add these methods to the class:

```python
    # -- live-frame tap API (MVP-2) --
    def add_viewer(self) -> None:
        with self._frame_lock:
            self._viewers += 1

    def remove_viewer(self) -> None:
        with self._frame_lock:
            self._viewers = max(0, self._viewers - 1)

    def set_overlay(self, on: bool) -> None:
        with self._frame_lock:
            self._overlay = on

    def latest_annotated(self) -> bytes | None:
        with self._frame_lock:
            return self._latest_annotated_jpeg

    def capture_still(self) -> tuple[bytes, int, int] | None:
        with self._frame_lock:
            frame = None if self._latest_full_bgr is None else self._latest_full_bgr.copy()
        if frame is None:
            return None
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            return None
        h, w = frame.shape[:2]
        return bytes(buf), int(w), int(h)

    def stats(self) -> dict:
        with self._frame_lock:
            return {
                "fps": round(self._fps_ema, 1),
                "tracking": self._tracking,
                "viewers": self._viewers,
            }

    def _tap_frame(self, frame_bgr, mono_ts: float) -> None:  # type: ignore[no-untyped-def]
        with self._frame_lock:
            self._latest_full_bgr = frame_bgr
            if self._last_mono is not None:
                dt = mono_ts - self._last_mono
                if dt > 0:
                    inst = 1.0 / dt
                    self._fps_ema = inst if self._fps_ema == 0 else 0.9 * self._fps_ema + 0.1 * inst
            self._last_mono = mono_ts
            want = self._viewers > 0 or self._overlay
            overlay = self._overlay
            dets = list(self._last_detections)
        if not want:
            return
        preview = frame_bgr
        if overlay and dets:
            preview = frame_bgr.copy()
            for d in dets:
                x, y, w, h = d.bbox
                cv2.rectangle(preview, (x, y), (x + w, y + h), (0, 255, 0), 2)
        ok, buf = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            with self._frame_lock:
                self._latest_annotated_jpeg = bytes(buf)
```

- [ ] **Step 5: Call the tap from the capture loop**

In `run_until_camera_exhausted`, immediately after the line `frame_bgr, ts = got`, add:

```python
                self._tap_frame(frame_bgr, ts)
```

In `_process_frame`, immediately after the `detections = find_motion(...)` call, add:

```python
        with self._frame_lock:
            self._last_detections = detections
            self._tracking = bool(detections)
```

- [ ] **Step 6: Run tests (new + MVP-1 runner suite must stay green)**

```bash
uv run pytest tests/unit/pipeline/test_runner_tap.py tests/integration/test_pipeline_runner.py -v
```

Expected: new 4 passed; existing runner tests still pass.

- [ ] **Step 7: Commit**

```bash
git add src/curbcam/pipeline/runner.py tests/unit/pipeline/test_runner_tap.py
git commit -m "feat(pipeline): live-frame tap (preview JPEG, capture_still, stats)"
```

---

### Task 8: Bounded EventBus subscriber queues

**Files:**
- Modify: `src/curbcam/pipeline/events.py`
- Create: `tests/unit/pipeline/test_event_bus_bounded.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/pipeline/test_event_bus_bounded.py
import asyncio

import pytest

from curbcam.pipeline.events import EventBus, EventEnvelope


@pytest.mark.asyncio
async def test_slow_subscriber_drops_oldest_without_raising() -> None:
    bus = EventBus(maxsize=4)
    q = bus.subscribe()
    # Publish more than maxsize without ever reading.
    for i in range(10):
        bus.publish(EventEnvelope(kind="event", payload={"i": i}))
    # Queue never exceeds maxsize, and publish never raised.
    assert q.qsize() == 4
    # Oldest were dropped — the surviving items are the most recent 4.
    survivors = [q.get_nowait().payload["i"] for _ in range(4)]
    assert survivors == [6, 7, 8, 9]


@pytest.mark.asyncio
async def test_subscribe_default_maxsize_is_bounded() -> None:
    bus = EventBus()
    q = bus.subscribe()
    assert q.maxsize > 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/pipeline/test_event_bus_bounded.py -v
```

Expected: FAIL (`EventBus()` takes no `maxsize`; unbounded queue keeps all 10).

- [ ] **Step 3: Modify `src/curbcam/pipeline/events.py`**

Change `EventBus.__init__` and `subscribe`/`publish`:

```python
class EventBus:
    def __init__(self, maxsize: int = 100) -> None:
        self._subs: list[asyncio.Queue[EventEnvelope]] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._maxsize = maxsize

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue[EventEnvelope]:
        q: asyncio.Queue[EventEnvelope] = asyncio.Queue(maxsize=self._maxsize)
        self._subs.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[EventEnvelope]) -> None:
        try:
            self._subs.remove(q)
        except ValueError:
            pass

    def publish(self, env: EventEnvelope) -> None:
        """Call from inside the asyncio loop. Drops oldest on a full queue."""
        for q in self._subs:
            while True:
                try:
                    q.put_nowait(env)
                    break
                except asyncio.QueueFull:
                    try:
                        q.get_nowait()  # drop oldest, retry
                    except asyncio.QueueEmpty:
                        break
```

(Leave `publish_threadsafe` unchanged.)

- [ ] **Step 4: Run tests (new + MVP-1 events/runner suites green)**

```bash
uv run pytest tests/unit/pipeline/test_event_bus_bounded.py tests/unit/pipeline/ -v
```

Expected: new 2 passed; existing pipeline tests still pass (default `maxsize` keeps the same API for `EventBus()`).

- [ ] **Step 5: Commit**

```bash
git add src/curbcam/pipeline/events.py tests/unit/pipeline/test_event_bus_bounded.py
git commit -m "feat(pipeline): bounded EventBus queues with oldest-drop backpressure"
```

---

### Task 9: Supervisor tap delegation + periodic stats publisher

**Files:**
- Modify: `src/curbcam/web/supervisor.py`
- Modify: `src/curbcam/web/app.py` (start a ~1 Hz stats task)
- Create: `tests/integration/web/test_supervisor_tap.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/web/test_supervisor_tap.py
def test_viewer_and_stats_delegate(supervisor) -> None:  # type: ignore[no-untyped-def]
    supervisor.start()
    try:
        supervisor.add_viewer()
        st = supervisor.stats()
        assert st["running"] is True
        assert st["viewers"] >= 1
        assert "fps" in st and "tracking" in st
    finally:
        supervisor.remove_viewer()
        supervisor.stop()


def test_capture_still_returns_none_when_stopped(supervisor) -> None:  # type: ignore[no-untyped-def]
    assert supervisor.capture_still() is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/integration/web/test_supervisor_tap.py -v
```

Expected: FAIL (`Supervisor` has no `add_viewer`).

- [ ] **Step 3: Add delegation + stats to `src/curbcam/web/supervisor.py`**

Replace the existing `stats` method and add the delegators (read `self._runner`
without the lifecycle lock — a plain attribute read, so viewers can be added
even during a restart):

```python
    # -- live-frame tap delegation (runner owns the slots) --
    def add_viewer(self) -> None:
        r = self._runner
        if r is not None:
            r.add_viewer()

    def remove_viewer(self) -> None:
        r = self._runner
        if r is not None:
            r.remove_viewer()

    def set_overlay(self, on: bool) -> None:
        r = self._runner
        if r is not None:
            r.set_overlay(on)

    def latest_annotated(self) -> bytes | None:
        r = self._runner
        return r.latest_annotated() if r is not None else None

    def capture_still(self) -> tuple[bytes, int, int] | None:
        r = self._runner
        return r.capture_still() if r is not None else None

    def stats(self) -> dict:
        uptime = 0.0 if self._started_at is None else time.monotonic() - self._started_at
        out: dict = {"uptime_s": round(uptime, 1), "running": self._runner is not None}
        r = self._runner
        if r is not None:
            out.update(r.stats())
        return out

    def publish_stats(self) -> None:
        """Publish a stats envelope (call from inside the asyncio loop)."""
        self._bus.publish(EventEnvelope(kind="stats", payload=self.stats()))
```

- [ ] **Step 4: Start the stats loop in `src/curbcam/web/app.py`**

Add this helper above `create_app`:

```python
async def _stats_loop(supervisor: Supervisor) -> None:
    while True:
        await asyncio.sleep(1.0)
        supervisor.publish_stats()
```

In the `lifespan` context manager, wrap startup/shutdown:

```python
        supervisor.bus.bind_loop(asyncio.get_running_loop())
        supervisor.start()
        stats_task = asyncio.create_task(_stats_loop(supervisor))
        try:
            yield
        finally:
            stats_task.cancel()
            supervisor.stop()
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/integration/web/test_supervisor_tap.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/curbcam/web/supervisor.py src/curbcam/web/app.py tests/integration/web/test_supervisor_tap.py
git commit -m "feat(web): supervisor tap delegation + 1 Hz stats publisher"
```

---

### Task 10: MJPEG stream + require_stream_auth

**Files:**
- Create: `src/curbcam/web/streams.py`
- Modify: `src/curbcam/web/deps.py` (`require_stream_auth`)
- Create: `src/curbcam/web/routes/stream.py`
- Modify: `src/curbcam/web/app.py` (register router)
- Create: `tests/unit/web/test_streams_mjpeg.py`
- Create: `tests/integration/web/test_streams.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/web/test_streams_mjpeg.py
import pytest

from curbcam.web.streams import mjpeg_generator


class _FakeSup:
    def __init__(self) -> None:
        self.viewers = 0

    def add_viewer(self) -> None:
        self.viewers += 1

    def remove_viewer(self) -> None:
        self.viewers -= 1

    def latest_annotated(self) -> bytes | None:
        return b"\xff\xd8JPEGDATA"


@pytest.mark.asyncio
async def test_mjpeg_generator_yields_multipart_jpeg_and_refcounts() -> None:
    sup = _FakeSup()
    gen = mjpeg_generator(sup, fps=1000.0)
    chunk = await gen.__anext__()
    assert b"--frame" in chunk
    assert b"image/jpeg" in chunk
    assert b"\xff\xd8" in chunk
    assert sup.viewers == 1
    await gen.aclose()
    assert sup.viewers == 0
```

```python
# tests/integration/web/test_streams.py
def test_mjpeg_requires_auth(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    # Configured (so the first-run gate does not redirect), but no session.
    supervisor.auth.set_password("x")
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    resp = client.get("/api/stream.mjpeg", follow_redirects=False)
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/web/test_streams_mjpeg.py tests/integration/web/test_streams.py -v
```

Expected: FAIL (`curbcam.web.streams` missing; no MJPEG route).

- [ ] **Step 3: Write `src/curbcam/web/streams.py`**

```python
"""MJPEG + SSE streaming generators (spec §8.4).

MJPEG: one shared annotated-frame slot, read at a fixed fps regardless of
camera rate. Viewer refcount is incremented on entry and decremented in a
finally so the runner stops encoding when nobody is watching.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import cv2
import numpy as np


def _placeholder_jpeg() -> bytes:
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(
        img, "no signal", (200, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.2,
        (255, 255, 255), 2, cv2.LINE_AA,
    )
    ok, buf = cv2.imencode(".jpg", img)
    return bytes(buf)


_PLACEHOLDER = _placeholder_jpeg()


async def mjpeg_generator(sup, fps: float = 5.0) -> AsyncIterator[bytes]:  # type: ignore[no-untyped-def]
    sup.add_viewer()
    delay = 1.0 / fps
    try:
        while True:
            frame = sup.latest_annotated() or _PLACEHOLDER
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n"
                + frame + b"\r\n"
            )
            await asyncio.sleep(delay)
    finally:
        sup.remove_viewer()


async def sse_generator(sup) -> AsyncIterator[bytes]:  # type: ignore[no-untyped-def]
    q = sup.bus.subscribe()
    try:
        while True:
            try:
                env = await asyncio.wait_for(q.get(), timeout=15.0)
            except asyncio.TimeoutError:
                yield b": keepalive\n\n"
                continue
            payload = json.dumps(env.payload)
            yield f"event: {env.kind}\ndata: {payload}\n\n".encode()
    finally:
        sup.bus.unsubscribe(q)
```

- [ ] **Step 4: Add `require_stream_auth` to `src/curbcam/web/deps.py`**

```python
from fastapi import Query


def require_stream_auth(request: Request, token: str | None = Query(default=None)) -> None:
    sup: Supervisor = request.app.state.supervisor
    if session_is_valid(sup, request):
        return
    if token and sup.auth.verify_stream_token(token):
        return
    raise HTTPException(status_code=401, detail="Not authenticated")
```

- [ ] **Step 5: Write `src/curbcam/web/routes/stream.py`**

```python
"""Live MJPEG preview. Accepts a session cookie OR a ?token= stream token."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from curbcam.web.deps import get_supervisor, require_stream_auth
from curbcam.web.streams import mjpeg_generator
from curbcam.web.supervisor import Supervisor

router = APIRouter()


@router.get("/api/stream.mjpeg")
def stream_mjpeg(
    _: None = Depends(require_stream_auth),
    sup: Supervisor = Depends(get_supervisor),
) -> StreamingResponse:
    resp = StreamingResponse(
        mjpeg_generator(sup),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return resp
```

- [ ] **Step 6: Register the router in `src/curbcam/web/app.py`**

Add `stream` to the routes import and `app.include_router(stream.router)`.

- [ ] **Step 7: Run tests**

```bash
uv run pytest tests/unit/web/test_streams_mjpeg.py tests/integration/web/test_streams.py -v
```

Expected: 2 passed.

- [ ] **Step 8: Commit**

```bash
git add src/curbcam/web/streams.py src/curbcam/web/deps.py src/curbcam/web/routes/stream.py src/curbcam/web/app.py tests/
git commit -m "feat(web): MJPEG stream endpoint + stream-token auth"
```

---

### Task 11: SSE event feed

**Files:**
- Create: `src/curbcam/web/routes/events.py` (SSE route only for now; query/CSV added in Slice D)
- Modify: `src/curbcam/web/app.py` (register router)
- Create: `tests/unit/web/test_streams_sse.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/web/test_streams_sse.py
import asyncio
from types import SimpleNamespace

import pytest

from curbcam.pipeline.events import EventBus, EventEnvelope
from curbcam.web.streams import sse_generator


@pytest.mark.asyncio
async def test_sse_generator_emits_published_event() -> None:
    bus = EventBus()
    sup = SimpleNamespace(bus=bus)
    gen = sse_generator(sup)
    task = asyncio.ensure_future(gen.__anext__())
    await asyncio.sleep(0.05)  # let the generator subscribe and block on get()
    bus.publish(EventEnvelope(kind="event", payload={"id": 7}))
    chunk = await asyncio.wait_for(task, timeout=2.0)
    assert b"event: event" in chunk
    assert b'"id": 7' in chunk
    await gen.aclose()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/web/test_streams_sse.py -v
```

Expected: PASS already? No — `sse_generator` exists (Task 10) but this verifies wiring; it should pass. If it fails, fix `sse_generator`. Then add the route below.

- [ ] **Step 3: Write `src/curbcam/web/routes/events.py`**

```python
"""Event feed (SSE) + history/CSV (history + CSV added in Slice D)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from curbcam.web.deps import get_supervisor, require_session
from curbcam.web.streams import sse_generator
from curbcam.web.supervisor import Supervisor

router = APIRouter()


@router.get("/api/events/stream")
def events_stream(
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> StreamingResponse:
    return StreamingResponse(sse_generator(sup), media_type="text/event-stream")
```

- [ ] **Step 4: Register the router in `src/curbcam/web/app.py`**

Add `events` to the routes import and `app.include_router(events.router)`.

- [ ] **Step 5: Run tests + full web suite so far**

```bash
uv run pytest tests/unit/web/ tests/integration/web/ -v
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/curbcam/web/routes/events.py src/curbcam/web/app.py tests/unit/web/test_streams_sse.py
git commit -m "feat(web): SSE event feed endpoint"
```

---

## Slice D — Viewing UI

### Task 12: Units conversion + formatting

**Files:**
- Create: `src/curbcam/web/units.py`
- Create: `tests/unit/web/test_units.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/web/test_units.py
import pytest

from curbcam.web.units import distance_to_mm, format_speed, kph_to_display


def test_kph_passthrough() -> None:
    assert kph_to_display(50.0, "kph") == pytest.approx(50.0)


def test_kph_to_mph() -> None:
    assert kph_to_display(50.0, "mph") == pytest.approx(31.0686, rel=1e-4)


def test_format_speed_includes_units() -> None:
    assert format_speed(50.0, "kph") == "50.0 kph"
    assert format_speed(50.0, "mph") == "31.1 mph"


def test_distance_to_mm_all_units() -> None:
    assert distance_to_mm(1, "mm") == pytest.approx(1.0)
    assert distance_to_mm(1, "in") == pytest.approx(25.4)
    assert distance_to_mm(1, "ft") == pytest.approx(304.8)
    assert distance_to_mm(1, "m") == pytest.approx(1000.0)


def test_distance_to_mm_rejects_unknown_unit() -> None:
    with pytest.raises(KeyError):
        distance_to_mm(1, "league")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/web/test_units.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'curbcam.web.units'`.

- [ ] **Step 3: Write `src/curbcam/web/units.py`**

```python
"""Display-unit conversion + real-world distance conversion.

Speeds are always stored in kph (the pipeline's native unit). The display
unit (kph | mph) is a server.units setting applied at render/export time.
Calibration distances are entered in m/ft/in/mm and converted to mm.
"""
from __future__ import annotations

_KPH_PER_MPH = 1.609344
_TO_MM = {"mm": 1.0, "in": 25.4, "ft": 304.8, "m": 1000.0}


def kph_to_display(kph: float, units: str) -> float:
    return kph if units == "kph" else kph / _KPH_PER_MPH


def format_speed(kph: float, units: str) -> str:
    return f"{kph_to_display(kph, units):.1f} {units}"


def distance_to_mm(value: float, unit: str) -> float:
    return value * _TO_MM[unit]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/web/test_units.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/curbcam/web/units.py tests/unit/web/test_units.py
git commit -m "feat(web): unit conversion + speed/distance formatting"
```

---

### Task 13: EventRepo.query (filters + keyset pagination) + delete_older_than

**Files:**
- Modify: `src/curbcam/storage/repositories.py`
- Create: `tests/unit/storage/test_event_query.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/storage/test_event_query.py
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/storage/test_event_query.py -v
```

Expected: FAIL with `ImportError: cannot import name 'EventFilter'`.

- [ ] **Step 3: Add to `src/curbcam/storage/repositories.py`**

Add imports at the top:

```python
from dataclasses import dataclass

from sqlalchemy import and_, or_, update
```

(Merge the `update` import with the existing one — it's already imported.)

Add the filter dataclass after the imports:

```python
@dataclass
class EventFilter:
    start: dt.datetime | None = None
    end: dt.datetime | None = None
    min_speed_kph: float | None = None
    max_speed_kph: float | None = None
    direction: str | None = None
```

Add these methods to `EventRepo`:

```python
    def query(
        self,
        f: EventFilter,
        *,
        cursor: tuple[dt.datetime, int] | None = None,
        limit: int = 50,
    ) -> list[Event]:
        """Newest-first, keyset-paginated on (ts_utc, id)."""
        with self._db.session() as s:
            q = s.query(Event)
            if f.start is not None:
                q = q.filter(Event.ts_utc >= f.start)
            if f.end is not None:
                q = q.filter(Event.ts_utc <= f.end)
            if f.min_speed_kph is not None:
                q = q.filter(Event.speed_kph >= f.min_speed_kph)
            if f.max_speed_kph is not None:
                q = q.filter(Event.speed_kph <= f.max_speed_kph)
            if f.direction is not None:
                q = q.filter(Event.direction == f.direction)
            if cursor is not None:
                cts, cid = cursor
                q = q.filter(
                    or_(Event.ts_utc < cts, and_(Event.ts_utc == cts, Event.id < cid))
                )
            return q.order_by(Event.ts_utc.desc(), Event.id.desc()).limit(limit).all()

    def delete_older_than(self, cutoff: dt.datetime) -> list[str]:
        """Delete event rows older than ``cutoff``; return the relative media
        paths (image + thumb) of the deleted rows so the caller can unlink the
        files. Rows are fetched (rather than bulk-deleted) precisely so the
        media paths can be returned — the privacy "delete old events" button
        must remove the JPEGs, not just the DB rows.
        """
        with self._db.session() as s:
            rows = s.query(Event).filter(Event.ts_utc < cutoff).all()
            paths = [p for r in rows for p in (r.image_path, r.thumb_path) if p]
            for r in rows:
                s.delete(r)
            s.commit()
            return paths
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/storage/test_event_query.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/curbcam/storage/repositories.py tests/unit/storage/test_event_query.py
git commit -m "feat(storage): EventRepo.query (filters + keyset pagination) + delete_older_than"
```

---

### Task 14: Templating/static wiring + Dashboard page

**Files:**
- Create: `src/curbcam/web/templating.py`
- Create: `src/curbcam/web/templates/base.html`
- Create: `src/curbcam/web/templates/dashboard.html`
- Create: `src/curbcam/web/templates/partials/event_card.html`
- Create: `src/curbcam/web/static/app.css`
- Create: `src/curbcam/web/static/app.js`
- Create: `src/curbcam/web/static/vendor/htmx.min.js` (download below)
- Create: `src/curbcam/web/routes/pages.py`
- Modify: `src/curbcam/web/app.py` (mount static + media, register pages)
- Create: `tests/integration/web/test_pages.py`

- [ ] **Step 1: Vendor htmx (no CDN on a LAN device)**

```bash
mkdir -p src/curbcam/web/static/vendor
curl -L https://unpkg.com/htmx.org@2.0.3/dist/htmx.min.js -o src/curbcam/web/static/vendor/htmx.min.js
```

Expected: a ~40 KB JS file. (If offline, copy from any cached htmx 2.x; the version is not load-bearing.)

- [ ] **Step 2: Write the failing test**

```python
# tests/integration/web/test_pages.py
import datetime as dt


def _configure(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": password})


def test_dashboard_renders_with_stream_and_events(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    supervisor.events.save(
        ts_utc=dt.datetime(2026, 5, 28, 12, 0, 0),
        speed_kph=42.0, direction="L2R", frame_count=10, track_len_px=200,
        image_path="events/e.jpg", thumb_path="thumbs/e.jpg", calibration_id=None,
    )
    resp = client.get("/")
    assert resp.status_code == 200
    assert "/api/stream.mjpeg" in resp.text
    assert "/api/events/stream" in resp.text
    assert "42.0 kph" in resp.text
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run pytest tests/integration/web/test_pages.py -v
```

Expected: FAIL (no `/` page route / templating).

- [ ] **Step 4: Write `src/curbcam/web/templating.py`**

```python
"""Shared Jinja2 environment + template filters."""
from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from curbcam.web.units import format_speed

_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(_DIR / "templates"))
templates.env.filters["speed"] = format_speed
```

- [ ] **Step 5: Write `src/curbcam/web/templates/base.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>curbcam{% block title %}{% endblock %}</title>
  <link rel="stylesheet" href="/static/app.css">
  <script src="/static/vendor/htmx.min.js" defer></script>
  <script src="/static/app.js" defer></script>
</head>
<body>
  <nav class="nav">
    <a href="/">Dashboard</a>
    <a href="/events">Events</a>
    <a href="/settings">Settings</a>
  </nav>
  <main class="main">{% block content %}{% endblock %}</main>
</body>
</html>
```

- [ ] **Step 6: Write `src/curbcam/web/templates/partials/event_card.html`**

```html
<article class="event-card" data-event-id="{{ e.id }}">
  <a href="/media/{{ e.image_path }}" target="_blank">
    <img src="/media/{{ e.thumb_path }}" alt="event {{ e.id }}" loading="lazy">
  </a>
  <div class="event-meta">
    <span class="speed">{{ e.speed_kph | speed(units) }}</span>
    <span class="dir">{{ ">>" if e.direction == "L2R" else "<<" }}</span>
    <time datetime="{{ e.ts_utc.isoformat() }}Z" class="ts"></time>
  </div>
</article>
```

- [ ] **Step 7: Write `src/curbcam/web/templates/dashboard.html`**

```html
{% extends "base.html" %}
{% block content %}
<section class="preview">
  <img id="preview" src="/api/stream.mjpeg" alt="live preview">
  <span id="tracking-pill" class="pill">idle</span>
</section>
<section id="event-list" class="event-list"
         data-sse="/api/events/stream" data-units="{{ units }}">
  {% for e in events %}
    {% include "partials/event_card.html" %}
  {% endfor %}
</section>
{% endblock %}
```

- [ ] **Step 8: Write `src/curbcam/web/static/app.css`**

```css
:root { font-family: system-ui, sans-serif; }
.nav { display: flex; gap: 1rem; padding: .75rem 1rem; background: #111; }
.nav a { color: #eee; text-decoration: none; }
.main { padding: 1rem; max-width: 980px; margin: 0 auto; }
.preview { position: relative; }
#preview { width: 100%; max-width: 640px; background: #000; border-radius: 8px; }
.pill { position: absolute; top: 8px; left: 8px; background: #333; color: #fff;
        padding: 2px 10px; border-radius: 999px; font-size: .8rem; }
.pill.active { background: #1a7f37; }
.event-list { display: grid; grid-template-columns: repeat(auto-fill, 320px); gap: 1rem; margin-top: 1rem; }
.event-card { width: 320px; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; }
.event-card img { width: 100%; display: block; }
.event-meta { display: flex; gap: .5rem; align-items: center; padding: .5rem; }
.event-meta .speed { font-weight: 600; }
.field-error { color: #b00020; font-size: .85rem; }
.badge-env { background: #555; color: #fff; font-size: .7rem; padding: 1px 6px; border-radius: 4px; }
```

- [ ] **Step 9: Write `src/curbcam/web/static/app.js`**

```javascript
// Render UTC timestamps in the browser's local zone.
function renderTimes(root) {
  root.querySelectorAll("time[datetime]").forEach((el) => {
    if (el.textContent) return;
    const d = new Date(el.getAttribute("datetime"));
    el.textContent = d.toLocaleString();
  });
}

document.addEventListener("DOMContentLoaded", () => {
  renderTimes(document);

  const list = document.getElementById("event-list");
  if (list && list.dataset.sse) {
    const units = list.dataset.units || "kph";
    const es = new EventSource(list.dataset.sse);
    es.addEventListener("event", (m) => {
      const ev = JSON.parse(m.data);
      const card = document.createElement("article");
      card.className = "event-card";
      const speed = units === "mph"
        ? (ev.speed_kph / 1.609344).toFixed(1)
        : ev.speed_kph.toFixed(1);
      const arrow = ev.direction === "L2R" ? ">>" : "<<";
      card.innerHTML =
        `<a href="/media/${ev.image_path}" target="_blank">` +
        `<img src="/media/${ev.thumb_path}" alt="event ${ev.id}"></a>` +
        `<div class="event-meta"><span class="speed">${speed} ${units}</span>` +
        `<span class="dir">${arrow}</span>` +
        `<time datetime="${ev.ts_utc}Z"></time></div>`;
      list.prepend(card);
      renderTimes(card);
    });
    es.addEventListener("stats", (m) => {
      const s = JSON.parse(m.data);
      const pill = document.getElementById("tracking-pill");
      if (!pill) return;
      pill.textContent = s.tracking ? "tracking" : `idle · ${s.fps ?? 0} fps`;
      pill.classList.toggle("active", !!s.tracking);
    });
  }
});
```

- [ ] **Step 10: Write `src/curbcam/web/routes/pages.py`**

```python
"""Server-rendered pages."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from curbcam.web.deps import get_supervisor, require_session
from curbcam.web.supervisor import Supervisor
from curbcam.web.templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    units = sup.config_store.load().server.units
    events = sup.events.list_recent(limit=10)
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "events": events, "units": units}
    )
```

- [ ] **Step 11: Mount static + media and register pages in `src/curbcam/web/app.py`**

Add imports:

```python
from pathlib import Path

from fastapi.staticfiles import StaticFiles

from curbcam.web.routes import auth, debug, events, pages, stream
```

In `create_app`, after creating `app` and before `return app`:

```python
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    supervisor.media_root.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=str(supervisor.media_root)), name="media")
    app.include_router(pages.router)
```

- [ ] **Step 12: Run tests**

```bash
uv run pytest tests/integration/web/test_pages.py -v
```

Expected: 1 passed.

- [ ] **Step 13: Commit**

```bash
git add src/curbcam/web/templating.py src/curbcam/web/templates/ src/curbcam/web/static/ src/curbcam/web/routes/pages.py src/curbcam/web/app.py tests/integration/web/test_pages.py
git commit -m "feat(web): templating/static wiring + dashboard page with SSE updates"
```

---

### Task 15: Events history page + filtered `/api/events` partial

**Files:**
- Modify: `src/curbcam/web/units.py` (add `display_to_kph`)
- Create: `src/curbcam/web/templates/events.html`
- Create: `src/curbcam/web/templates/partials/events_rows.html`
- Modify: `src/curbcam/web/routes/pages.py` (`/events` page)
- Modify: `src/curbcam/web/routes/events.py` (`/api/events` partial + filter parsing)
- Create: `tests/integration/web/test_events_history.py`

- [ ] **Step 1: Add `display_to_kph` to `src/curbcam/web/units.py`**

```python
def display_to_kph(value: float, units: str) -> float:
    return value if units == "kph" else value * _KPH_PER_MPH
```

- [ ] **Step 2: Write the failing test**

```python
# tests/integration/web/test_events_history.py
import datetime as dt


def _configure(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": password})


def _seed(supervisor, n: int = 5) -> None:  # type: ignore[no-untyped-def]
    for i in range(n):
        supervisor.events.save(
            ts_utc=dt.datetime(2026, 5, 28, 12, i, 0),
            speed_kph=20.0 + i * 10,
            direction="L2R" if i % 2 == 0 else "R2L",
            frame_count=10, track_len_px=200,
            image_path=f"events/e_{i}.jpg", thumb_path=f"thumbs/e_{i}.jpg",
            calibration_id=None,
        )


def test_events_page_renders_filter_form(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    resp = client.get("/events")
    assert resp.status_code == 200
    assert 'name="direction"' in resp.text


def test_api_events_filters_by_direction(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    _seed(supervisor)
    resp = client.get("/api/events", params={"direction": "R2L"})
    assert resp.status_code == 200
    # 2 R2L events (indices 1,3); cards carry data-event-id.
    assert resp.text.count("data-event-id") == 2


def test_api_events_requires_auth(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("pw")
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    resp = client.get("/api/events", follow_redirects=False)
    assert resp.status_code == 401
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run pytest tests/integration/web/test_events_history.py -v
```

Expected: FAIL (no `/events` page, no `/api/events`).

- [ ] **Step 4: Write `src/curbcam/web/templates/partials/events_rows.html`**

```html
{% for e in events %}
  {% include "partials/event_card.html" %}
{% endfor %}
{% if next_cursor %}
<button class="load-more"
        hx-get="/api/events?{{ query }}&cursor={{ next_cursor }}"
        hx-target="this" hx-swap="outerHTML">Load more</button>
{% endif %}
```

- [ ] **Step 5: Write `src/curbcam/web/templates/events.html`**

```html
{% extends "base.html" %}
{% block content %}
<h1>Events</h1>
<form class="filters" hx-get="/api/events" hx-target="#rows" hx-swap="innerHTML">
  <label>From <input type="date" name="start"></label>
  <label>To <input type="date" name="end"></label>
  <label>Min speed <input type="number" step="0.1" name="min_speed"></label>
  <label>Max speed <input type="number" step="0.1" name="max_speed"></label>
  <label>Direction
    <select name="direction">
      <option value="">Any</option>
      <option value="L2R">&gt;&gt;</option>
      <option value="R2L">&lt;&lt;</option>
    </select>
  </label>
  <button type="submit">Filter</button>
  <a class="csv" href="/api/events.csv">Export CSV</a>
</form>
<section id="rows" class="event-list" data-units="{{ units }}">
  {% include "partials/events_rows.html" %}
</section>
{% endblock %}
```

- [ ] **Step 6: Add the `/events` page to `src/curbcam/web/routes/pages.py`**

```python
@router.get("/events", response_class=HTMLResponse)
def events_page(
    request: Request,
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    from curbcam.storage.repositories import EventFilter

    units = sup.config_store.load().server.units
    limit = 24
    rows = sup.events.query(EventFilter(), limit=limit)
    next_cursor = (
        f"{rows[-1].ts_utc.isoformat()}|{rows[-1].id}" if len(rows) == limit else ""
    )
    return templates.TemplateResponse(
        "events.html",
        {"request": request, "events": rows, "units": units,
         "next_cursor": next_cursor, "query": ""},
    )
```

- [ ] **Step 7: Add the filter parser + `/api/events` partial to `src/curbcam/web/routes/events.py`**

Add imports:

```python
import datetime as dt
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import HTMLResponse

from curbcam.storage.repositories import EventFilter
from curbcam.web.templating import templates
from curbcam.web.units import display_to_kph
```

Add helpers + route:

```python
_PAGE = 24


def _parse_filter(
    sup: Supervisor,
    start: str | None,
    end: str | None,
    min_speed: float | None,
    max_speed: float | None,
    direction: str | None,
) -> tuple[EventFilter, str]:
    units = sup.config_store.load().server.units
    f = EventFilter(direction=direction or None)
    if start:
        f.start = dt.datetime.combine(dt.date.fromisoformat(start), dt.time.min)
    if end:
        f.end = dt.datetime.combine(dt.date.fromisoformat(end), dt.time.max)
    if min_speed is not None:
        f.min_speed_kph = display_to_kph(min_speed, units)
    if max_speed is not None:
        f.max_speed_kph = display_to_kph(max_speed, units)
    return f, units


def _parse_cursor(cursor: str | None) -> tuple[dt.datetime, int] | None:
    if not cursor:
        return None
    ts_str, id_str = cursor.split("|", 1)
    return dt.datetime.fromisoformat(ts_str), int(id_str)


@router.get("/api/events", response_class=HTMLResponse)
def api_events(
    request: Request,
    start: str | None = None,
    end: str | None = None,
    min_speed: float | None = None,
    max_speed: float | None = None,
    direction: str | None = None,
    cursor: str | None = None,
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    f, units = _parse_filter(sup, start, end, min_speed, max_speed, direction)
    rows = sup.events.query(f, cursor=_parse_cursor(cursor), limit=_PAGE)
    next_cursor = (
        f"{rows[-1].ts_utc.isoformat()}|{rows[-1].id}" if len(rows) == _PAGE else ""
    )
    query = urlencode(
        {k: v for k, v in {
            "start": start, "end": end, "min_speed": min_speed,
            "max_speed": max_speed, "direction": direction,
        }.items() if v is not None}
    )
    return templates.TemplateResponse(
        "partials/events_rows.html",
        {"request": request, "events": rows, "units": units,
         "next_cursor": next_cursor, "query": query},
    )
```

- [ ] **Step 8: Run tests**

```bash
uv run pytest tests/integration/web/test_events_history.py -v
```

Expected: 3 passed.

- [ ] **Step 9: Commit**

```bash
git add src/curbcam/web/units.py src/curbcam/web/templates/ src/curbcam/web/routes/ tests/integration/web/test_events_history.py
git commit -m "feat(web): events history page + filtered /api/events partial"
```

---

### Task 16: CSV export

**Files:**
- Modify: `src/curbcam/web/routes/events.py` (`/api/events.csv`)
- Create: `tests/integration/web/test_csv.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/web/test_csv.py
import datetime as dt


def _configure(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": password})


def test_csv_export_headers_and_unit_conversion(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    # Switch display units to mph so we can assert conversion.
    s = supervisor.config_store.load()
    s = s.model_copy(update={"server": s.server.model_copy(update={"units": "mph"})})
    supervisor.config_store.save(s)
    _configure(client, supervisor)
    supervisor.events.save(
        ts_utc=dt.datetime(2026, 5, 28, 12, 0, 0),
        speed_kph=80.4672, direction="L2R", frame_count=10, track_len_px=200,
        image_path="events/e.jpg", thumb_path="thumbs/e.jpg", calibration_id=None,
    )
    resp = client.get("/api/events.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers.get("content-disposition", "")
    lines = resp.text.strip().splitlines()
    assert lines[0] == "id,ts_utc,speed,units,direction,frame_count,track_len_px,image_path"
    # 80.4672 kph == 50.0 mph
    assert ",50.0,mph," in lines[1]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/integration/web/test_csv.py -v
```

Expected: FAIL (no `/api/events.csv`).

- [ ] **Step 3: Add the CSV route to `src/curbcam/web/routes/events.py`**

Add imports:

```python
import csv
import io

from fastapi.responses import StreamingResponse

from curbcam.web.units import kph_to_display
```

Add the route:

```python
@router.get("/api/events.csv")
def api_events_csv(
    start: str | None = None,
    end: str | None = None,
    min_speed: float | None = None,
    max_speed: float | None = None,
    direction: str | None = None,
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> StreamingResponse:
    f, units = _parse_filter(sup, start, end, min_speed, max_speed, direction)

    def rows():  # type: ignore[no-untyped-def]
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(
            ["id", "ts_utc", "speed", "units", "direction",
             "frame_count", "track_len_px", "image_path"]
        )
        yield buf.getvalue()
        buf.seek(0); buf.truncate(0)

        cursor: tuple[dt.datetime, int] | None = None
        while True:
            page = sup.events.query(f, cursor=cursor, limit=500)
            if not page:
                break
            for e in page:
                w.writerow([
                    e.id, f"{e.ts_utc.isoformat()}Z",
                    round(kph_to_display(float(e.speed_kph), units), 1), units,
                    e.direction, e.frame_count, e.track_len_px, e.image_path,
                ])
            yield buf.getvalue()
            buf.seek(0); buf.truncate(0)
            cursor = (page[-1].ts_utc, page[-1].id)

    return StreamingResponse(
        rows(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=curbcam-events.csv"},
    )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/integration/web/test_csv.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/curbcam/web/routes/events.py tests/integration/web/test_csv.py
git commit -m "feat(web): streamed CSV export honoring display units"
```

---

## Slice E — Settings

### Task 17: ConfigStore raw read/write + Settings page (GET)

**Files:**
- Modify: `src/curbcam/config/store.py` (`load_raw`, `save_raw`)
- Create: `src/curbcam/web/settings_form.py` (field-descriptor builder, shared GET/POST)
- Create: `src/curbcam/web/templates/settings.html`
- Create: `src/curbcam/web/templates/partials/settings_form.html`
- Modify: `src/curbcam/web/routes/pages.py` (`/settings`)
- Create: `tests/unit/config/test_store_raw.py`
- Create: `tests/integration/web/test_settings_page.py`

- [ ] **Step 1: Write the failing store test**

```python
# tests/unit/config/test_store_raw.py
from pathlib import Path

from curbcam.config.store import ConfigStore


def test_load_raw_returns_plain_yaml_without_env(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "curbcam.yaml"
    store = ConfigStore(path)
    store.load()  # writes defaults
    monkeypatch.setenv("CURBCAM_CAMERA__SOURCE", "rtsp://env-host/s")
    raw = store.load_raw()
    # Raw YAML reflects the file, NOT the env override.
    assert raw["camera"]["source"] != "rtsp://env-host/s"


def test_save_raw_round_trips(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "curbcam.yaml"
    store = ConfigStore(path)
    store.load()
    raw = store.load_raw()
    raw["server"]["units"] = "mph"
    store.save_raw(raw)
    assert store.load_raw()["server"]["units"] == "mph"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/config/test_store_raw.py -v
```

Expected: FAIL (`ConfigStore` has no `load_raw`).

- [ ] **Step 3: Add `load_raw`/`save_raw` to `src/curbcam/config/store.py`**

```python
    def load_raw(self) -> dict:
        """Return the YAML dict as-on-disk, WITHOUT env-var overlay.

        Used by the settings UI so saving never bakes an env-shadowed
        value into the file (spec §5). Returns defaults if the file is
        absent.
        """
        if not self._path.exists():
            return Settings().model_dump(mode="json")
        with self._path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def save_raw(self, data: dict) -> None:
        self._write_yaml(data)
```

- [ ] **Step 4: Write the failing page test**

```python
# tests/integration/web/test_settings_page.py
def _configure(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": password})


def test_settings_page_shows_fields(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert 'name="camera.source"' in resp.text
    assert 'name="detector.min_area_px"' in resp.text


def test_env_shadowed_field_is_readonly(client, supervisor, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    monkeypatch.setenv("CURBCAM_CAMERA__SOURCE", "rtsp://env-host/s")
    resp = client.get("/settings")
    assert "set via environment" in resp.text
```

- [ ] **Step 5: Run test to verify it fails**

```bash
uv run pytest tests/integration/web/test_settings_page.py -v
```

Expected: FAIL (no `/settings` route).

- [ ] **Step 6: Write `src/curbcam/web/settings_form.py`**

```python
"""Build settings field descriptors for the form (shared by GET + POST-error).

Each descriptor carries label/help (from config.defaults.FIELD_LABELS), the
current value, an input kind, and whether the field is shadowed by an env var
(rendered read-only). crop is excluded — it is set by the alignment wizard.
"""
from __future__ import annotations

import os
from typing import Any

from curbcam.config.defaults import FIELD_LABELS

PRIMARY: list[tuple[str, str]] = [
    ("camera.source", "text"),
    ("camera.resolution", "resolution"),
    ("camera.fps_target", "number"),
    ("server.units", "select:kph,mph"),
    ("server.min_event_speed_kph", "number"),
]
ADVANCED: list[tuple[str, str]] = [
    ("detector.min_area_px", "number"),
    ("detector.min_track_frames", "number"),
    ("detector.max_dist_px", "number"),
    ("retention.max_events_per_day", "number"),
    ("retention.max_total_disk_mb", "number"),
    ("server.log_level", "select:DEBUG,INFO,WARNING"),
]


def _env_key(dotted: str) -> str:
    section, field = dotted.split(".", 1)
    return f"CURBCAM_{section.upper()}__{field.upper()}"


def _get(raw: dict, dotted: str) -> Any:
    section, field = dotted.split(".", 1)
    return raw.get(section, {}).get(field)


def _format_value(value: Any, kind: str) -> str:
    if kind == "resolution" and isinstance(value, (list, tuple)) and len(value) == 2:
        return f"{value[0]}x{value[1]}"
    return "" if value is None else str(value)


def _descriptor(raw: dict, dotted: str, kind: str, errors: dict[str, str]) -> dict:
    label, help_text = FIELD_LABELS.get(dotted, (dotted, ""))
    options = kind.split(":", 1)[1].split(",") if kind.startswith("select:") else []
    return {
        "key": dotted,
        "label": label,
        "help": help_text,
        "kind": "select" if kind.startswith("select:") else kind,
        "options": options,
        "value": _format_value(_get(raw, dotted), kind),
        "env": os.environ.get(_env_key(dotted)) is not None,
        "error": errors.get(dotted),
    }


def build_groups(raw: dict, errors: dict[str, str] | None = None) -> dict[str, list[dict]]:
    errors = errors or {}
    return {
        "primary": [_descriptor(raw, k, kind, errors) for k, kind in PRIMARY],
        "advanced": [_descriptor(raw, k, kind, errors) for k, kind in ADVANCED],
    }
```

- [ ] **Step 7: Write `src/curbcam/web/templates/partials/settings_form.html`**

```html
<form id="settings-form" hx-post="/api/settings" hx-target="#settings-form" hx-swap="outerHTML">
  {% for group_name, fields in groups.items() %}
  <fieldset>
    <legend>{{ group_name|capitalize }}</legend>
    {% for f in fields %}
    <div class="setting">
      <label for="{{ f.key }}">{{ f.label }}</label>
      {% if f.kind == "select" %}
        <select id="{{ f.key }}" name="{{ f.key }}" {% if f.env %}disabled{% endif %}>
          {% for opt in f.options %}
          <option value="{{ opt }}" {% if opt == f.value %}selected{% endif %}>{{ opt }}</option>
          {% endfor %}
        </select>
      {% else %}
        <input id="{{ f.key }}" name="{{ f.key }}" value="{{ f.value }}"
               {% if f.kind == "number" %}inputmode="decimal"{% endif %}
               {% if f.env %}readonly{% endif %}>
      {% endif %}
      <small class="help">{{ f.help }}</small>
      {% if f.env %}<span class="badge-env">set via environment</span>{% endif %}
      {% if f.error %}<span class="field-error">{{ f.error }}</span>{% endif %}
    </div>
    {% endfor %}
  </fieldset>
  {% endfor %}
  <button type="submit">Save &amp; restart</button>
  {% if saved %}<span class="saved-ok">Saved — detector restarting…</span>{% endif %}
</form>
```

- [ ] **Step 8: Write `src/curbcam/web/templates/settings.html`**

```html
{% extends "base.html" %}
{% block content %}
<h1>Settings</h1>
{% include "partials/settings_form.html" %}

<section class="integrations">
  <h2>Integrations — stream tokens</h2>
  <form hx-post="/api/tokens" hx-target="#token-list" hx-swap="afterbegin">
    <input name="label" placeholder="e.g. Home Assistant" required>
    <button type="submit">Mint token</button>
  </form>
  <ul id="token-list">
    {% for t in tokens %}<li data-token-id="{{ t.id }}">{{ t.label }}
      <button hx-delete="/api/tokens/{{ t.id }}" hx-target="closest li" hx-swap="outerHTML">Revoke</button></li>{% endfor %}
  </ul>
</section>

<section class="danger">
  <h2>Delete old events</h2>
  <form hx-post="/api/events/purge" hx-confirm="Delete events older than the given days?">
    <input type="number" name="days" value="30" min="1">
    <button type="submit">Delete</button>
  </form>
</section>
{% endblock %}
```

- [ ] **Step 9: Add the `/settings` page to `src/curbcam/web/routes/pages.py`**

```python
@router.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    from curbcam.web.settings_form import build_groups

    raw = sup.config_store.load_raw()
    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "groups": build_groups(raw),
         "tokens": sup.auth.list_stream_tokens(), "saved": False},
    )
```

- [ ] **Step 10: Run tests**

```bash
uv run pytest tests/unit/config/test_store_raw.py tests/integration/web/test_settings_page.py -v
```

Expected: store 2 passed, page 2 passed.

- [ ] **Step 11: Commit**

```bash
git add src/curbcam/config/store.py src/curbcam/web/settings_form.py src/curbcam/web/templates/ src/curbcam/web/routes/pages.py tests/
git commit -m "feat(web): settings page (GET) + ConfigStore raw read/write"
```

---

### Task 18: POST /api/settings — validate, save, graceful restart

**Files:**
- Create: `src/curbcam/web/routes/settings.py`
- Modify: `src/curbcam/web/app.py` (register router)
- Create: `tests/integration/web/test_settings_save.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/web/test_settings_save.py
def _configure(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": password})


def _form(supervisor, **overrides) -> dict:  # type: ignore[no-untyped-def]
    raw = supervisor.config_store.load_raw()
    data = {
        "camera.source": overrides.get("source", raw["camera"]["source"]),
        "camera.resolution": overrides.get("resolution", "1280x720"),
        "camera.fps_target": overrides.get("fps_target", "15"),
        "server.units": overrides.get("units", "kph"),
        "server.min_event_speed_kph": overrides.get("min_event_speed_kph", "5"),
        "detector.min_area_px": "800",
        "detector.min_track_frames": "5",
        "detector.max_dist_px": "100",
        "retention.max_events_per_day": "500",
        "retention.max_total_disk_mb": "5000",
        "server.log_level": "INFO",
    }
    return data


def test_valid_save_persists_and_restarts(client, supervisor, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    restarts: list[int] = []
    monkeypatch.setattr(supervisor, "restart", lambda: restarts.append(1))
    resp = client.post("/api/settings", data=_form(supervisor, units="mph"))
    assert resp.status_code == 200
    assert supervisor.config_store.load_raw()["server"]["units"] == "mph"
    assert restarts == [1]


def test_invalid_value_returns_422_with_inline_error(client, supervisor, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    monkeypatch.setattr(supervisor, "restart", lambda: None)
    resp = client.post("/api/settings", data=_form(supervisor, fps_target="-3"))
    assert resp.status_code == 422
    assert "field-error" in resp.text
    # Bad value was NOT persisted.
    assert float(supervisor.config_store.load_raw()["camera"]["fps_target"]) > 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/integration/web/test_settings_save.py -v
```

Expected: FAIL (no `/api/settings` route).

- [ ] **Step 3: Write `src/curbcam/web/routes/settings.py`**

```python
"""Settings save: parse form -> validate -> save raw YAML -> graceful restart.

Env-shadowed fields are read-only in the form and therefore not posted, so
the saved YAML never bakes in an env value (spec §5).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from curbcam.config.schema import Settings
from curbcam.web.deps import get_supervisor, require_session
from curbcam.web.settings_form import build_groups
from curbcam.web.supervisor import Supervisor
from curbcam.web.templating import templates

router = APIRouter()


def _set_nested(d: dict, dotted: str, value: object) -> None:
    section, field = dotted.split(".", 1)
    d.setdefault(section, {})[field] = value


def _coerce(key: str, value: str) -> object:
    if key == "camera.resolution":
        w, h = value.lower().split("x", 1)
        return [int(w), int(h)]
    return value  # Pydantic coerces numeric strings; selects/text pass through


@router.post("/api/settings", response_class=HTMLResponse)
async def save_settings(
    request: Request,
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    form = await request.form()
    raw = sup.config_store.load_raw()
    for key, value in form.items():
        if "." in key:
            try:
                _set_nested(raw, key, _coerce(key, str(value)))
            except ValueError:
                pass  # malformed resolution surfaces as a validation error below

    try:
        Settings.model_validate(raw)
    except ValidationError as exc:
        errors: dict[str, str] = {}
        for e in exc.errors():
            dotted = ".".join(str(p) for p in e["loc"][:2])
            errors[dotted] = e["msg"]
        return templates.TemplateResponse(
            "partials/settings_form.html",
            {"request": request, "groups": build_groups(raw, errors), "saved": False},
            status_code=422,
        )

    sup.config_store.save_raw(raw)
    await run_in_threadpool(sup.restart)
    return templates.TemplateResponse(
        "partials/settings_form.html",
        {"request": request, "groups": build_groups(raw), "saved": True},
    )
```

- [ ] **Step 4: Register the router in `src/curbcam/web/app.py`**

Add `settings` to the routes import and `app.include_router(settings.router)`.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/integration/web/test_settings_save.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/curbcam/web/routes/settings.py src/curbcam/web/app.py tests/integration/web/test_settings_save.py
git commit -m "feat(web): POST /api/settings validate+save+graceful restart"
```

---

### Task 19: Stream-token mint/revoke + event purge

**Files:**
- Modify: `src/curbcam/web/routes/settings.py` (token + purge routes)
- Create: `tests/integration/web/test_tokens_purge.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/web/test_tokens_purge.py
import datetime as dt


def _configure(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": password})


def test_mint_then_revoke_token(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    resp = client.post("/api/tokens", data={"label": "Home Assistant"})
    assert resp.status_code == 200
    assert "Home Assistant" in resp.text
    tokens = supervisor.auth.list_stream_tokens()
    assert len(tokens) == 1
    tid = tokens[0]["id"]
    resp = client.delete(f"/api/tokens/{tid}")
    assert resp.status_code == 200
    assert supervisor.auth.list_stream_tokens() == []


def test_purge_old_events(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    old = dt.datetime(2020, 1, 1, 0, 0, 0)
    supervisor.events.save(
        ts_utc=old, speed_kph=30.0, direction="L2R", frame_count=10,
        track_len_px=100, image_path="events/o.jpg", thumb_path="thumbs/o.jpg",
        calibration_id=None,
    )
    resp = client.post("/api/events/purge", data={"days": "30"})
    assert resp.status_code in (200, 204)
    from curbcam.storage.repositories import EventFilter
    assert supervisor.events.query(EventFilter()) == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/integration/web/test_tokens_purge.py -v
```

Expected: FAIL (no token/purge routes).

- [ ] **Step 3: Add the routes to `src/curbcam/web/routes/settings.py`**

Add imports:

```python
import datetime as dt

from fastapi import Form, Response
from markupsafe import escape
```

Add routes:

```python
@router.post("/api/tokens", response_class=HTMLResponse)
def mint_token(
    request: Request,
    label: str = Form(...),
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    token_id, raw_token = sup.auth.mint_stream_token(label)
    # Escape the user-supplied label to prevent stored XSS (the admin is the
    # only writer, but defense-in-depth is cheap). raw_token is server-minted.
    safe_label = escape(label)
    # Show the raw token once; it is never retrievable again.
    html = (
        f'<li data-token-id="{token_id}">{safe_label} '
        f'<code class="token-once">{raw_token}</code> '
        f'<button hx-delete="/api/tokens/{token_id}" '
        f'hx-target="closest li" hx-swap="outerHTML">Revoke</button></li>'
    )
    return HTMLResponse(html)


@router.delete("/api/tokens/{token_id}")
def revoke_token(
    token_id: str,
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> Response:
    sup.auth.revoke_stream_token(token_id)
    return Response(status_code=200)


@router.post("/api/events/purge")
def purge_events(
    days: int = Form(...),
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> Response:
    cutoff = dt.datetime.now(dt.UTC).replace(tzinfo=None) - dt.timedelta(days=days)
    # Delete rows AND their media files — a privacy button that left the JPEGs
    # on disk would defeat its purpose (spec §15).
    for rel in sup.events.delete_older_than(cutoff):
        (sup.media_root / rel).unlink(missing_ok=True)
    return Response(status_code=204)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/integration/web/test_tokens_purge.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/curbcam/web/routes/settings.py tests/integration/web/test_tokens_purge.py
git commit -m "feat(web): stream-token mint/revoke + event purge"
```

---

## Slice F — Wizards

### Task 20: Calibration capture endpoint

**Files:**
- Create: `src/curbcam/web/routes/calibration.py` (capture only; measure in Task 21)
- Modify: `src/curbcam/web/app.py` (register router)
- Create: `tests/integration/web/test_calibration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/web/test_calibration.py
import time


def _login(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    client.post("/api/auth/login", data={"password": password})


def test_capture_returns_jpeg(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _login(client, supervisor)
    # The pipeline thread needs a moment to read the first frame.
    deadline = time.monotonic() + 3.0
    resp = client.post("/api/calibration/capture")
    while resp.status_code == 503 and time.monotonic() < deadline:
        resp = client.post("/api/calibration/capture")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content[:2] == b"\xff\xd8"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/integration/web/test_calibration.py -v
```

Expected: FAIL (no `/api/calibration/capture`).

- [ ] **Step 3: Write `src/curbcam/web/routes/calibration.py`**

```python
"""Calibration wizard endpoints (spec §8.7).

capture: freeze the current live frame as a JPEG for measurement. The
frontend reads the source resolution from the returned image's
naturalWidth/naturalHeight, so no separate dimensions payload is needed.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from curbcam.web.deps import get_supervisor, require_session
from curbcam.web.supervisor import Supervisor

router = APIRouter()


@router.post("/api/calibration/capture")
def capture(
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> Response:
    got = sup.capture_still()
    if got is None:
        raise HTTPException(status_code=503, detail="No frame available yet")
    jpeg, _w, _h = got
    return Response(content=jpeg, media_type="image/jpeg")
```

- [ ] **Step 4: Register the router in `src/curbcam/web/app.py`**

Add `calibration` to the routes import and `app.include_router(calibration.router)`.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/integration/web/test_calibration.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add src/curbcam/web/routes/calibration.py src/curbcam/web/app.py tests/integration/web/test_calibration.py
git commit -m "feat(web): calibration capture endpoint"
```

---

### Task 21: Calibration measure endpoint (two-scale)

**Files:**
- Modify: `src/curbcam/web/routes/calibration.py` (`/api/calibration/measure`)
- Create: `tests/integration/web/test_calibration_measure.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/web/test_calibration_measure.py
def _login(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    client.post("/api/auth/login", data={"password": password})


def test_measure_computes_mm_per_px_l2r(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _login(client, supervisor)
    # 100 px apart, 5 m real distance -> 5000 mm / 100 px = 50 mm/px.
    body = {
        "points": [[100, 100], [200, 100]],
        "distance": 5.0, "units": "m", "direction": "L2R",
    }
    resp = client.post("/api/calibration/measure", json=body)
    assert resp.status_code == 200
    assert resp.json()["mm_per_px"] == 50.0
    active = supervisor.calibrations.get_active()
    assert active is not None
    assert float(active.mm_per_px_l2r) == 50.0
    # R2L defaults to the same until separately calibrated.
    assert float(active.mm_per_px_r2l) == 50.0


def test_measure_rejects_out_of_bounds_points(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _login(client, supervisor)
    # Default resolution is 1280x720; y=9999 is out of bounds.
    body = {
        "points": [[10, 10], [20, 9999]],
        "distance": 1.0, "units": "m", "direction": "L2R",
    }
    resp = client.post("/api/calibration/measure", json=body)
    assert resp.status_code == 422


def test_measure_second_direction_preserves_first(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _login(client, supervisor)
    client.post("/api/calibration/measure", json={
        "points": [[100, 100], [200, 100]], "distance": 5.0, "units": "m", "direction": "L2R",
    })
    client.post("/api/calibration/measure", json={
        "points": [[100, 100], [300, 100]], "distance": 5.0, "units": "m", "direction": "R2L",
    })
    active = supervisor.calibrations.get_active()
    assert float(active.mm_per_px_l2r) == 50.0      # preserved
    assert float(active.mm_per_px_r2l) == 25.0      # 5000 / 200
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/integration/web/test_calibration_measure.py -v
```

Expected: FAIL (no `/api/calibration/measure`).

- [ ] **Step 3: Add the measure route to `src/curbcam/web/routes/calibration.py`**

Add imports:

```python
import json
import math

from pydantic import BaseModel, field_validator

from curbcam.web.units import distance_to_mm


class MeasureIn(BaseModel):
    points: list[tuple[float, float]]
    distance: float
    units: str
    direction: str

    @field_validator("points")
    @classmethod
    def _exactly_two(cls, v: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(v) != 2:
            raise ValueError("exactly two points required")
        return v

    @field_validator("direction")
    @classmethod
    def _dir(cls, v: str) -> str:
        if v not in ("L2R", "R2L"):
            raise ValueError("direction must be L2R or R2L")
        return v
```

Add the route:

```python
@router.post("/api/calibration/measure")
def measure(
    body: MeasureIn,
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> dict:
    settings = sup.config_store.load()
    w, h = settings.camera.resolution
    for (x, y) in body.points:
        if not (0 <= x <= w and 0 <= y <= h):
            raise HTTPException(status_code=422, detail="point out of frame bounds")

    (x0, y0), (x1, y1) = body.points
    pixel_distance = math.hypot(x1 - x0, y1 - y0)
    if pixel_distance <= 0:
        raise HTTPException(status_code=422, detail="points must differ")
    try:
        distance_mm = distance_to_mm(body.distance, body.units)
    except KeyError:
        raise HTTPException(status_code=422, detail="unknown distance unit") from None
    if distance_mm <= 0:
        raise HTTPException(status_code=422, detail="distance must be positive")

    mm_per_px = round(distance_mm / pixel_distance, 6)

    active = sup.calibrations.get_active()
    l2r = float(active.mm_per_px_l2r) if active else None
    r2l = float(active.mm_per_px_r2l) if active else None
    if body.direction == "L2R":
        l2r = mm_per_px
        r2l = r2l if r2l is not None else mm_per_px
    else:
        r2l = mm_per_px
        l2r = l2r if l2r is not None else mm_per_px

    cal = sup.calibrations.save_new_active(
        mm_per_px_l2r=l2r,
        mm_per_px_r2l=r2l,
        reference_distance_mm=distance_mm,
        reference_points_json=json.dumps(body.points),
    )
    return {"mm_per_px": mm_per_px, "direction": body.direction, "calibration_id": cal.id}
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/integration/web/test_calibration_measure.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/curbcam/web/routes/calibration.py tests/integration/web/test_calibration_measure.py
git commit -m "feat(web): calibration measure endpoint with two-scale handling"
```

---

### Task 22: Calibration wizard page + canvas JS

**Files:**
- Create: `src/curbcam/web/templates/setup/calibrate.html`
- Create: `src/curbcam/web/static/calibrate.js`
- Modify: `src/curbcam/web/routes/pages.py` (`/setup/calibrate`)
- Create: `tests/integration/web/test_wizard_pages.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/web/test_wizard_pages.py
def _login(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    client.post("/api/auth/login", data={"password": password})


def test_calibrate_wizard_page_renders(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _login(client, supervisor)
    resp = client.get("/setup/calibrate")
    assert resp.status_code == 200
    assert 'id="capture"' in resp.text
    assert "calibrate.js" in resp.text


def test_align_wizard_page_renders(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _login(client, supervisor)
    resp = client.get("/setup/align")
    assert resp.status_code == 200
    assert 'id="align-canvas"' in resp.text
    assert "align.js" in resp.text
```

(The second assertion covers Task 23's page; it will pass once Task 23 lands.)

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/integration/web/test_wizard_pages.py::test_calibrate_wizard_page_renders -v
```

Expected: FAIL (no `/setup/calibrate`).

- [ ] **Step 3: Write `src/curbcam/web/templates/setup/calibrate.html`**

```html
{% extends "base.html" %}
{% block content %}
<h1>Calibration</h1>
<ol class="wizard-help">
  <li>Place a known-length object in view (fence panel, parked car, chalk line).</li>
  <li>Capture, then click its two ends.</li>
  <li>Enter the real-world distance and which direction this lane carries.</li>
</ol>
<button id="capture">Capture reference frame</button>
<div class="canvas-wrap">
  <img id="frame" alt="reference frame">
  <canvas id="cal-canvas"></canvas>
</div>
<div class="cal-controls">
  <span id="pixel-distance">0 px</span>
  <button id="undo" type="button">Undo point</button>
  <button id="reset" type="button">Start over</button>
  <label>Distance <input id="distance" type="number" step="0.01" min="0"></label>
  <label>Units
    <select id="units"><option>m</option><option>ft</option><option>in</option><option>mm</option></select>
  </label>
  <label>Direction
    <select id="direction"><option value="L2R">&gt;&gt;</option><option value="R2L">&lt;&lt;</option></select>
  </label>
  <button id="submit" type="button">Save calibration</button>
</div>
<p id="result" class="result"></p>
<script src="/static/calibrate.js" defer></script>
{% endblock %}
```

- [ ] **Step 4: Write `src/curbcam/web/static/calibrate.js`**

```javascript
// Calibration wizard: capture a frozen frame, click two points (scaled from
// display coords back to SOURCE coords — the off-by-2x footgun in spec §8.7),
// submit a real-world distance. Uses safe DOM APIs (no innerHTML).
(() => {
  const frame = document.getElementById("frame");
  const canvas = document.getElementById("cal-canvas");
  const ctx = canvas.getContext("2d");
  const pixelOut = document.getElementById("pixel-distance");
  const result = document.getElementById("result");
  let points = []; // SOURCE-coordinate points

  function scale() {
    // naturalWidth is the SOURCE width of the captured JPEG.
    return frame.naturalWidth / frame.clientWidth;
  }

  function redraw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const s = scale();
    ctx.fillStyle = "red";
    ctx.strokeStyle = "red";
    ctx.lineWidth = 2;
    points.forEach((p) => {
      ctx.beginPath();
      ctx.arc(p[0] / s, p[1] / s, 5, 0, Math.PI * 2);
      ctx.fill();
    });
    if (points.length === 2) {
      ctx.beginPath();
      ctx.moveTo(points[0][0] / s, points[0][1] / s);
      ctx.lineTo(points[1][0] / s, points[1][1] / s);
      ctx.stroke();
      const dx = points[1][0] - points[0][0];
      const dy = points[1][1] - points[0][1];
      pixelOut.textContent = `${Math.round(Math.hypot(dx, dy))} px`;
    } else {
      pixelOut.textContent = "0 px";
    }
  }

  document.getElementById("capture").addEventListener("click", async () => {
    const resp = await fetch("/api/calibration/capture", { method: "POST" });
    if (!resp.ok) { result.textContent = "No frame yet — try again."; return; }
    const blob = await resp.blob();
    frame.src = URL.createObjectURL(blob);
    points = [];
  });

  frame.addEventListener("load", () => {
    canvas.width = frame.clientWidth;
    canvas.height = frame.clientHeight;
    redraw();
  });

  canvas.addEventListener("click", (e) => {
    if (points.length >= 2) return;
    const rect = canvas.getBoundingClientRect();
    const s = scale();
    points.push([(e.clientX - rect.left) * s, (e.clientY - rect.top) * s]);
    redraw();
  });

  document.getElementById("undo").addEventListener("click", () => { points.pop(); redraw(); });
  document.getElementById("reset").addEventListener("click", () => { points = []; redraw(); });

  document.getElementById("submit").addEventListener("click", async () => {
    if (points.length !== 2) { result.textContent = "Click two points first."; return; }
    const body = {
      points,
      distance: parseFloat(document.getElementById("distance").value),
      units: document.getElementById("units").value,
      direction: document.getElementById("direction").value,
    };
    const resp = await fetch("/api/calibration/measure", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (resp.ok) {
      const data = await resp.json();
      result.textContent =
        `Saved: ${data.mm_per_px} mm/px (${data.direction}). ` +
        `Drive a known-speed vehicle past to verify, then go to the dashboard.`;
    } else {
      result.textContent = "Could not save — check your inputs.";
    }
  });
})();
```

- [ ] **Step 5: Add the `/setup/calibrate` page to `src/curbcam/web/routes/pages.py`**

```python
@router.get("/setup/calibrate", response_class=HTMLResponse)
def calibrate_wizard(
    request: Request,
    _: None = Depends(require_session),
) -> HTMLResponse:
    return templates.TemplateResponse("setup/calibrate.html", {"request": request})
```

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/integration/web/test_wizard_pages.py::test_calibrate_wizard_page_renders -v
```

Expected: 1 passed.

- [ ] **Step 7: Commit**

```bash
git add src/curbcam/web/templates/setup/calibrate.html src/curbcam/web/static/calibrate.js src/curbcam/web/routes/pages.py tests/integration/web/test_wizard_pages.py
git commit -m "feat(web): calibration wizard page + canvas point-picking JS"
```

---

### Task 23: Alignment wizard + POST /api/crop

**Files:**
- Modify: `src/curbcam/web/routes/stream.py` (honor `?overlay=1`)
- Create: `src/curbcam/web/routes/crop.py`
- Modify: `src/curbcam/web/app.py` (register crop router)
- Create: `src/curbcam/web/templates/setup/align.html`
- Create: `src/curbcam/web/static/align.js`
- Modify: `src/curbcam/web/routes/pages.py` (`/setup/align`)
- Create: `tests/integration/web/test_crop.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/web/test_crop.py
def _login(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    client.post("/api/auth/login", data={"password": password})


def test_crop_saves_and_restarts(client, supervisor, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _login(client, supervisor)
    restarts: list[int] = []
    monkeypatch.setattr(supervisor, "restart", lambda: restarts.append(1))
    resp = client.post("/api/crop", json={"x0": 100, "y0": 50, "x1": 500, "y1": 400})
    assert resp.status_code in (200, 204)
    assert supervisor.config_store.load_raw()["detector"]["crop"] == [100, 50, 500, 400]
    assert restarts == [1]


def test_crop_rejects_inverted_rect(client, supervisor, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _login(client, supervisor)
    monkeypatch.setattr(supervisor, "restart", lambda: None)
    resp = client.post("/api/crop", json={"x0": 500, "y0": 400, "x1": 100, "y1": 50})
    assert resp.status_code == 422


def test_crop_rejects_out_of_bounds(client, supervisor, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _login(client, supervisor)
    monkeypatch.setattr(supervisor, "restart", lambda: None)
    resp = client.post("/api/crop", json={"x0": 0, "y0": 0, "x1": 99999, "y1": 400})
    assert resp.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/integration/web/test_crop.py -v
```

Expected: FAIL (no `/api/crop`).

- [ ] **Step 3: Write `src/curbcam/web/routes/crop.py`**

```python
"""Alignment wizard: save the detection crop rectangle (spec §8.6).

Rect is in SOURCE-frame coordinates (the JS scales display->source). On
save: validate against the configured resolution, persist detector.crop,
graceful restart.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from curbcam.config.schema import Settings
from curbcam.web.deps import get_supervisor, require_session
from curbcam.web.supervisor import Supervisor

router = APIRouter()


class CropIn(BaseModel):
    x0: int
    y0: int
    x1: int
    y1: int


@router.post("/api/crop")
async def save_crop(
    body: CropIn,
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> Response:
    settings = sup.config_store.load()
    w, h = settings.camera.resolution
    if not (0 <= body.x0 < body.x1 <= w and 0 <= body.y0 < body.y1 <= h):
        raise HTTPException(status_code=422, detail="invalid crop rectangle")

    raw = sup.config_store.load_raw()
    raw.setdefault("detector", {})["crop"] = [body.x0, body.y0, body.x1, body.y1]
    Settings.model_validate(raw)  # defense in depth
    sup.config_store.save_raw(raw)
    await run_in_threadpool(sup.restart)
    return Response(status_code=204)
```

- [ ] **Step 4: Honor `?overlay=1` in `src/curbcam/web/routes/stream.py`**

Replace the `stream_mjpeg` function with one that toggles the overlay flag:

```python
from fastapi import Query


@router.get("/api/stream.mjpeg")
def stream_mjpeg(
    overlay: bool = Query(default=False),
    _: None = Depends(require_stream_auth),
    sup: Supervisor = Depends(get_supervisor),
) -> StreamingResponse:
    sup.set_overlay(overlay)
    resp = StreamingResponse(
        mjpeg_generator(sup),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return resp
```

- [ ] **Step 5: Write `src/curbcam/web/templates/setup/align.html`**

```html
{% extends "base.html" %}
{% block content %}
<h1>Alignment</h1>
<p>Drag a rectangle over the area where vehicles pass. Toggle the overlay to see
what the detector currently sees.</p>
<label><input type="checkbox" id="overlay-toggle"> Show motion-detection overlay</label>
<div class="canvas-wrap">
  <img id="align-frame" src="/api/stream.mjpeg" alt="live preview">
  <canvas id="align-canvas"></canvas>
</div>
<button id="save-crop" type="button">Save detection region</button>
<a class="next" href="/setup/calibrate">Next: calibrate &raquo;</a>
<p id="align-result" class="result"></p>
<script src="/static/align.js" defer></script>
{% endblock %}
```

- [ ] **Step 6: Write `src/curbcam/web/static/align.js`**

```javascript
// Alignment wizard: drag a crop rect over the live MJPEG, scale display->source,
// POST it. Safe DOM only.
(() => {
  const frame = document.getElementById("align-frame");
  const canvas = document.getElementById("align-canvas");
  const ctx = canvas.getContext("2d");
  const result = document.getElementById("align-result");
  let start = null;
  let rect = null; // SOURCE coords [x0,y0,x1,y1]

  function scale() { return frame.naturalWidth / frame.clientWidth; }

  function sizeCanvas() {
    canvas.width = frame.clientWidth;
    canvas.height = frame.clientHeight;
  }
  frame.addEventListener("load", sizeCanvas);
  window.addEventListener("resize", sizeCanvas);

  function toDisp(v) { return v / scale(); }

  function redraw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!rect) return;
    ctx.strokeStyle = "lime";
    ctx.lineWidth = 2;
    ctx.strokeRect(toDisp(rect[0]), toDisp(rect[1]),
                   toDisp(rect[2] - rect[0]), toDisp(rect[3] - rect[1]));
  }

  canvas.addEventListener("mousedown", (e) => {
    const r = canvas.getBoundingClientRect();
    start = [e.clientX - r.left, e.clientY - r.top];
  });
  canvas.addEventListener("mousemove", (e) => {
    if (!start) return;
    const r = canvas.getBoundingClientRect();
    const s = scale();
    const cur = [e.clientX - r.left, e.clientY - r.top];
    rect = [
      Math.round(Math.min(start[0], cur[0]) * s),
      Math.round(Math.min(start[1], cur[1]) * s),
      Math.round(Math.max(start[0], cur[0]) * s),
      Math.round(Math.max(start[1], cur[1]) * s),
    ];
    redraw();
  });
  window.addEventListener("mouseup", () => { start = null; });

  document.getElementById("overlay-toggle").addEventListener("change", (e) => {
    frame.src = e.target.checked ? "/api/stream.mjpeg?overlay=1" : "/api/stream.mjpeg";
  });

  document.getElementById("save-crop").addEventListener("click", async () => {
    if (!rect) { result.textContent = "Drag a rectangle first."; return; }
    const resp = await fetch("/api/crop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ x0: rect[0], y0: rect[1], x1: rect[2], y1: rect[3] }),
    });
    result.textContent = resp.ok ? "Saved — detector restarting." : "Invalid region.";
  });
})();
```

- [ ] **Step 7: Add the `/setup/align` page to `src/curbcam/web/routes/pages.py`, register crop router in `app.py`**

In `pages.py`:

```python
@router.get("/setup/align", response_class=HTMLResponse)
def align_wizard(
    request: Request,
    _: None = Depends(require_session),
) -> HTMLResponse:
    return templates.TemplateResponse("setup/align.html", {"request": request})
```

In `app.py`: add `crop` to the routes import and `app.include_router(crop.router)`.

- [ ] **Step 8: Run tests**

```bash
uv run pytest tests/integration/web/test_crop.py tests/integration/web/test_wizard_pages.py -v
```

Expected: crop 3 passed, wizard pages 2 passed.

- [ ] **Step 9: Commit**

```bash
git add src/curbcam/web/routes/crop.py src/curbcam/web/routes/stream.py src/curbcam/web/templates/setup/align.html src/curbcam/web/static/align.js src/curbcam/web/routes/pages.py src/curbcam/web/app.py tests/integration/web/test_crop.py
git commit -m "feat(web): alignment wizard + crop save + overlay stream toggle"
```

---

### Task 24: First-run wizard flow

**Files:**
- Modify: `src/curbcam/web/middleware.py` (exempt `/api/setup`)
- Create: `src/curbcam/web/routes/setup.py`
- Modify: `src/curbcam/web/app.py` (register setup router)
- Modify: `src/curbcam/web/routes/pages.py` (`/setup` host page)
- Create: `src/curbcam/web/templates/setup/index.html`
- Create: `src/curbcam/web/templates/setup/password.html`
- Create: `src/curbcam/web/templates/setup/configure.html`
- Create: `tests/integration/web/test_first_run.py`

- [ ] **Step 1: Exempt `/api/setup` in `src/curbcam/web/middleware.py`**

Add `"/api/setup"` to `_EXEMPT_PREFIXES` (the password step runs before any
session exists).

- [ ] **Step 2: Write the failing test**

```python
# tests/integration/web/test_first_run.py
def test_setup_shows_password_form_when_unconfigured(client) -> None:  # type: ignore[no-untyped-def]
    resp = client.get("/setup")
    assert resp.status_code == 200
    assert 'name="password"' in resp.text


def test_setup_password_sets_password_and_session(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    resp = client.post("/api/setup/password", data={"password": "s3cret"})
    assert resp.status_code == 200
    assert supervisor.auth.has_password() is True
    assert "curbcam_session" in resp.cookies
    assert 'name="source"' in resp.text  # configure panel follows


def test_setup_camera_saves_source_and_restarts(client, supervisor, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("s3cret")
    client.post("/api/auth/login", data={"password": "s3cret"})
    restarts: list[int] = []
    monkeypatch.setattr(supervisor, "restart", lambda: restarts.append(1))
    resp = client.post("/api/setup/camera", data={"source": "usb:0"})
    assert resp.status_code == 200
    assert supervisor.config_store.load_raw()["camera"]["source"] == "usb:0"
    assert restarts == [1]


def test_setup_redirects_home_when_fully_configured(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("s3cret")
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": "s3cret"})
    resp = client.get("/setup", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run pytest tests/integration/web/test_first_run.py -v
```

Expected: FAIL (no `/setup` page / `/api/setup/*`).

- [ ] **Step 4: Write the setup templates**

`src/curbcam/web/templates/setup/password.html`:

```html
<form id="setup-step" hx-post="/api/setup/password" hx-target="#setup-step" hx-swap="outerHTML">
  <h2>1 · Set an admin password</h2>
  <p>This is the only account. You'll use it to reach the dashboard and settings.</p>
  <input type="password" name="password" placeholder="Choose a password" required minlength="6">
  <button type="submit">Set password</button>
</form>
```

`src/curbcam/web/templates/setup/configure.html`:

```html
<div id="setup-step">
  <h2>2 · Before you start</h2>
  <p>Speed cameras capture people and vehicles in public spaces. <strong>Check your
  local laws</strong> before pointing this at a road. Nothing leaves this device.</p>
  <label><input type="checkbox" id="ack"> I understand</label>

  <h2>3 · Camera source</h2>
  <form hx-post="/api/setup/camera" hx-target="#camera-result" hx-swap="innerHTML">
    <input name="source" placeholder="picamera2:0 | usb:0 | rtsp://... | file:./fixtures" required>
    <button type="submit">Use this camera</button>
  </form>
  <span id="camera-result"></span>

  <h2>4 · Confirm preview</h2>
  <img id="setup-preview" src="/api/stream.mjpeg" alt="live preview" style="max-width:640px">

  <h2>5 · Align &amp; calibrate</h2>
  <a href="/setup/align">Set detection region &raquo;</a>
  <a href="/setup/calibrate">Calibrate speed &raquo;</a>
</div>
```

`src/curbcam/web/templates/setup/index.html`:

```html
{% extends "base.html" %}
{% block content %}
<h1>curbcam setup</h1>
{% if need_password %}
  {% include "setup/password.html" %}
{% else %}
  {% include "setup/configure.html" %}
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Write `src/curbcam/web/routes/setup.py`**

```python
"""First-run wizard endpoints. /api/setup/* is gate-exempt."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from curbcam.web.deps import get_supervisor, issue_session, require_session
from curbcam.web.supervisor import Supervisor
from curbcam.web.templating import templates

router = APIRouter()


@router.post("/api/setup/password", response_class=HTMLResponse)
def setup_password(
    request: Request,
    password: str = Form(..., min_length=6),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    sup.auth.set_password(password)
    resp = templates.TemplateResponse("setup/configure.html", {"request": request})
    issue_session(sup, resp)
    return resp


@router.post("/api/setup/camera", response_class=HTMLResponse)
async def setup_camera(
    source: str = Form(...),
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    raw = sup.config_store.load_raw()
    raw.setdefault("camera", {})["source"] = source
    sup.config_store.save_raw(raw)
    await run_in_threadpool(sup.restart)
    return HTMLResponse("Camera saved — preview below should update.")
```

- [ ] **Step 6: Add the `/setup` host page to `src/curbcam/web/routes/pages.py`, register router**

In `pages.py` (note: this page intentionally does NOT require a session — it is
the entry point before any password exists):

```python
from fastapi.responses import HTMLResponse, RedirectResponse


@router.get("/setup", response_class=HTMLResponse)
def setup_page(
    request: Request,
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse | RedirectResponse:
    if sup.auth.has_password() and sup.calibrations.get_active() is not None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        "setup/index.html",
        {"request": request, "need_password": not sup.auth.has_password()},
    )
```

In `app.py`: add `setup` to the routes import and `app.include_router(setup.router)`.

- [ ] **Step 7: Run tests**

```bash
uv run pytest tests/integration/web/test_first_run.py -v
```

Expected: 4 passed.

- [ ] **Step 8: Commit**

```bash
git add src/curbcam/web/middleware.py src/curbcam/web/routes/setup.py src/curbcam/web/routes/pages.py src/curbcam/web/app.py src/curbcam/web/templates/setup/ tests/integration/web/test_first_run.py
git commit -m "feat(web): first-run wizard flow (password, privacy, camera, preview, links)"
```

---

### Task 25: Playwright smoke test for the calibration wizard

**Files:**
- Modify: `pyproject.toml` (register the `e2e` marker)
- Create: `tests/e2e/__init__.py`
- Create: `tests/e2e/conftest.py`
- Create: `tests/e2e/test_calibrate_smoke.py`

- [ ] **Step 1: Install the browser**

```bash
uv run playwright install chromium
```

Expected: chromium downloaded. (If this fails in the environment, the test
auto-skips via `importorskip`; it is excluded from the default suite by marker.)

- [ ] **Step 2: Register the marker in `pyproject.toml`**

Under `[tool.pytest.ini_options]`, add:

```toml
markers = ["e2e: browser end-to-end tests (require playwright browsers)"]
```

- [ ] **Step 3: Write `tests/e2e/conftest.py`**

```python
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
    s = s.model_copy(update={"camera": s.camera.model_copy(
        update={"source": f"file:{frames}", "resolution": (640, 480)})})
    store.save(s)
    auth = AuthStore(tmp_path / "auth.json")
    auth.set_password("pw")

    sup = Supervisor(config_store=store, db=db, bus=EventBus(),
                     media_root=tmp_path / "media", auth_store=auth)
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
```

- [ ] **Step 4: Write `tests/e2e/test_calibrate_smoke.py`**

```python
import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402


@pytest.mark.e2e
def test_calibration_wizard_creates_active_calibration(live_server) -> None:  # type: ignore[no-untyped-def]
    base_url, sup = live_server
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:  # browser not installed in this environment
            pytest.skip("chromium not installed")
        ctx = browser.new_context()
        # Authenticate (shares cookies with the browser context).
        ctx.request.post(f"{base_url}/api/auth/login", form={"password": "pw"})
        page = ctx.new_page()
        page.goto(f"{base_url}/setup/calibrate")

        page.click("#capture")
        page.wait_for_function("document.getElementById('frame').naturalWidth > 0")

        canvas = page.locator("#cal-canvas")
        box = canvas.bounding_box()
        # Two points 100 display-px apart. With a 640-wide source shown at ~640,
        # scale ~= 1, so ~100 source px.
        page.mouse.click(box["x"] + 100, box["y"] + 100)
        page.mouse.click(box["x"] + 200, box["y"] + 100)

        page.fill("#distance", "5")
        page.select_option("#units", "m")
        page.select_option("#direction", "L2R")
        page.click("#submit")
        page.wait_for_selector("#result:has-text('Saved')")
        browser.close()

    active = sup.calibrations.get_active()
    assert active is not None
    # 5 m over ~100 px ≈ 50 mm/px; allow slack for canvas scaling/rounding.
    assert 30.0 <= float(active.mm_per_px_l2r) <= 90.0
```

- [ ] **Step 5: Run the e2e test**

```bash
uv run pytest tests/e2e/ -v -m e2e
```

Expected: 1 passed (or skipped if chromium is unavailable).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/e2e/
git commit -m "test(web): Playwright smoke test for the calibration wizard"
```

---

## Slice G — Finalize

### Task 26: Lint, types, coverage, README, push

**Files:**
- Modify: `README.md`
- No new source files.

- [ ] **Step 1: Ruff**

```bash
cd D:/curbcam
uv run ruff check .
uv run ruff format .
uv run ruff check .
```

Expected: no findings. Fix any inline.

- [ ] **Step 2: mypy strict**

```bash
uv run mypy src/curbcam
```

Expected: `Success: no issues found`. The web modules use FastAPI patterns
mypy-strict dislikes (untyped `Request.form()` values, dependency defaults);
the plan's code already carries targeted `# type: ignore[...]` where needed.
Fix any remaining errors inline rather than blanket-ignoring a module.

- [ ] **Step 3: Full test suite + coverage**

```bash
uv run pytest --cov=curbcam --cov-report=term-missing
```

Expected: all pass (e2e skips without chromium). Coverage on `src/curbcam/web/`
should be ≥ 85%. If a route is under-covered, add a focused integration test in
`tests/integration/web/` rather than lowering the bar.

- [ ] **Step 4: Update `README.md`**

Replace the **Status** line and add a new "Run the web app (MVP-2)" section
above "Camera sources":

```markdown
**Status:** MVP-2 (web app: dashboard, live preview, wizards) — see
[`docs/specs/2026-05-28-curbcam-mvp-2-web.md`](docs/specs/2026-05-28-curbcam-mvp-2-web.md).

## Run the web app (MVP-2)

```bash
uv run curbcam serve            # http://<pi-ip>:8000
```

On first launch every page redirects to a setup wizard:

1. Set a single admin password.
2. Acknowledge the privacy notice (check your local laws — §15).
3. Pick a camera source and confirm the live preview.
4. **Align** — drag a rectangle over the road to set the detection region.
5. **Calibrate** — capture a frame, click the two ends of a known-length
   object, enter the real-world distance and travel direction.

After setup: a dashboard with live MJPEG + an event feed, a filterable Events
history with CSV export, and Settings (saving restarts the detector). Embed the
preview elsewhere (e.g. Home Assistant) with a revocable stream token from
**Settings → Integrations**: `http://<pi-ip>:8000/api/stream.mjpeg?token=...`.

### Mounting for best accuracy

Speed accuracy is limited by perspective and centroid jitter, not pixel count.
Two tips that beat any software setting:

- **Angle the camera somewhat down the road**, not straight across — this
  flattens the near/far depth gradient and reduces perspective error.
- **Calibrate each direction** against a reference at that lane's distance; the
  two-scale model (`mm_per_px_l2r` / `mm_per_px_r2l`) exists for exactly the
  near-lane/far-lane depth difference.

(A perspective-homography calibration is planned for a future "calibration v2";
it is the lever that would tighten accuracy further.)
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: MVP-2 web app quick-start + mounting guidance"
```

- [ ] **Step 6: Push the branch and open a PR**

```bash
git push -u origin <your-mvp-2-branch>
gh pr create --title "MVP-2: web layer (serve, wizards, live streams)" \
  --body "Implements docs/specs/2026-05-28-curbcam-mvp-2-web.md. See plan: docs/plans/2026-05-28-curbcam-mvp-2-web.md"
```

Expected: PR opened. After review + green CI, merge. Tag `v0.2.0-mvp-2` after merge.

---

## Security notes (carry into implementation)

- **No untrusted innerHTML.** `calibrate.js` and `align.js` write only via
  `textContent`/canvas APIs. `app.js` builds the dashboard event card by
  interpolating server-generated fields (`image_path`, `thumb_path`, numeric
  `speed_kph`, `ts_utc`, `id`) — all server-origin, not user input. If event
  payloads ever gain a user-influenced string field, switch that card builder to
  `document.createElement` + `textContent`/`setAttribute` rather than an
  innerHTML template.
- **Escape the one user-writable string.** The stream-token `label` (Task 19) is
  the only user-supplied value rendered into HTML; wrap it in
  `markupsafe.escape(...)` before interpolation (noted in the task).
- **Stream-token leak guard.** `/api/stream.mjpeg` sets
  `Referrer-Policy: strict-origin-when-cross-origin` so an embedded `?token=`
  cannot leak via `Referer` (Task 10).

---

## What ships at the end of MVP-2

- `curbcam serve` — one process running the detector pipeline + a LAN-only web UI.
- First-run, alignment, and calibration wizards replace manual CLI calibration.
- Dashboard (live MJPEG + SSE event feed + tracking pill), Events history with
  filters + CSV export, Settings with validate-and-graceful-restart.
- Single admin password (Argon2), signed session cookie, revocable stream tokens.
- Live-frame tap + bounded event queues + serialized restarts (the co-plan
  hardening) all covered by tests.
- Unit + integration tests (no hardware), one Playwright smoke test; ruff + mypy
  strict clean; ≥85% coverage on `web/`.

Deferred by design: Docker/mDNS/three-command install → **MVP-3**; perspective
homography → **calibration v2**; alerts/graphs/cloud sync/ALPR → v0.2+.










