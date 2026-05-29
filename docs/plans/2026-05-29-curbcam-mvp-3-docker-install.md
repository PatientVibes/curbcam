# curbcam MVP-3 — Docker / mDNS / Install Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a three-command Docker install — `curl` the compose file, `docker compose up -d`, browse `http://curbcam.local:8080` — backed by a multi-arch (arm64+amd64) image published to GHCR, with mDNS discovery, a health endpoint, and a migrate-on-boot entrypoint so `docker compose pull` upgrades cleanly.

**Architecture:** A new pure `src/curbcam/discovery/` package (LAN-IP detection + in-process `python-zeroconf` publisher) and a gate-exempt `/healthz` route. mDNS + a startup banner wire into the `serve` CLI path **only** (never `create_app`, which stays a pure, side-effect-free function — every MVP-2 test depends on this). A new `curbcam db upgrade` runs real Alembic migrations. Container artifacts (`Dockerfile`, `docker-compose.yml`, `docker-entrypoint.sh`) run as root under host networking; a `docker.yml` CI workflow builds+smoke-tests amd64 on every PR and pushes multi-arch to GHCR on `v*` tags.

**Tech Stack:** Python 3.12, `zeroconf>=0.132` (new), Alembic (existing), Typer/FastAPI (existing), Docker buildx + QEMU, GitHub Actions, GHCR.

**Reference:** Design spec at `docs/specs/2026-05-29-curbcam-mvp-3-docker-install.md` (cited §N). Plan style: `docs/plans/2026-05-28-curbcam-mvp-2-web.md`.

---

## Slices (independently shippable groups)

- **Slice A — Discovery primitives + /healthz** (Tasks 1–4): `zeroconf` dep, `detect_lan_ip`, `MDNSPublisher`, `/healthz` + gate exemption.
- **Slice B — serve wiring + db upgrade** (Tasks 5–6): mDNS lifecycle + banner in `serve`; `curbcam db upgrade`.
- **Slice C — Container artifacts** (Tasks 7–10): `Dockerfile`, `docker-entrypoint.sh`, `docker-compose.yml`, `.dockerignore`, `.env.example`.
- **Slice D — CI/CD** (Task 11): `docker.yml` — amd64 build+smoke on PR, multi-arch→GHCR on tag.
- **Slice E — Docs + finalize** (Task 12): README rewrite, design-spec sync, gates, tag.

---

## File Structure

```
src/curbcam/discovery/
├── __init__.py        # exports detect_lan_ip, MDNSPublisher
├── net.py             # detect_lan_ip() -> str
└── mdns.py            # MDNSPublisher (python-zeroconf wrapper)
src/curbcam/web/routes/
└── health.py          # GET /healthz (unauthenticated, gate-exempt)
tests/unit/discovery/
├── __init__.py
├── test_net.py
└── test_mdns.py
tests/integration/web/
└── test_health.py
Dockerfile             # multi-stage, multi-arch, root, no picamera2
docker-entrypoint.sh   # db upgrade → serve (migrate-before-serve)
docker-compose.yml     # the downloaded artifact (host net)
.dockerignore
.env.example
.github/workflows/docker.yml
```

**Modified existing files:**
- `pyproject.toml` — add `zeroconf` dep + `docker` pytest marker.
- `src/curbcam/web/app.py` — register the health router.
- `src/curbcam/web/middleware.py` — add `/healthz` to `_EXEMPT_PREFIXES`.
- `src/curbcam/cli.py` — `serve` gains `--mdns/--no-mdns` + banner; add `db upgrade`.
- `README.md`, `docs/specs/2026-05-28-curbcam-design.md` — docs sync (Task 12).

---

## Slice A — Discovery primitives + /healthz

### Task 1: zeroconf dependency + discovery package skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `src/curbcam/discovery/__init__.py`
- Create: `tests/unit/discovery/__init__.py`

- [ ] **Step 1: Add the dependency + marker to `pyproject.toml`**

In `[project].dependencies`, add (alphabetical-ish, after `uvicorn[standard]`):

```toml
    "zeroconf>=0.132",
```

In `[tool.pytest.ini_options].markers`, add the `docker` marker alongside `e2e`:

```toml
markers = [
    "e2e: browser end-to-end tests (require playwright browsers)",
    "docker: tests that build/run the Docker image (excluded from default run)",
]
```

And extend `addopts` so `docker` tests are excluded by default (mirrors the `e2e` exclusion):

```toml
addopts = "-ra --strict-markers --strict-config -m 'not e2e and not docker'"
```

- [ ] **Step 2: Install**

```bash
cd D:/curbcam
uv pip install -e ".[dev]"
```

Expected: resolves and installs `zeroconf` without error.

- [ ] **Step 3: Create `src/curbcam/discovery/__init__.py`**

```python
"""Process-level discovery: LAN-IP detection + in-process mDNS publishing.

Kept out of web/ — discovery is a deployment concern, orchestrated by the
CLI (spec §3), never imported by request handlers.
"""

from curbcam.discovery.mdns import MDNSPublisher
from curbcam.discovery.net import detect_lan_ip

__all__ = ["MDNSPublisher", "detect_lan_ip"]
```

(This import will fail until Tasks 2–3 create the modules — that is expected; do not run anything yet.)

- [ ] **Step 4: Create `tests/unit/discovery/__init__.py` (empty)**

```python
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/curbcam/discovery/__init__.py tests/unit/discovery/__init__.py
git commit -m "build(discovery): add zeroconf dep + discovery package skeleton"
```

---

### Task 2: `detect_lan_ip()`

**Files:**
- Create: `src/curbcam/discovery/net.py`
- Create: `tests/unit/discovery/test_net.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/discovery/test_net.py
"""detect_lan_ip uses a UDP socket's chosen source address (no packet sent)
and falls back to loopback on any OSError. Both paths are tested without
real networking by substituting a fake socket."""
from __future__ import annotations

import socket

import curbcam.discovery.net as net


class _FakeSocket:
    def __init__(self, *_a, **_k) -> None:
        self.closed = False

    def connect(self, _addr) -> None:
        pass

    def getsockname(self) -> tuple[str, int]:
        return ("192.168.1.42", 12345)

    def close(self) -> None:
        self.closed = True


class _RaisingSocket(_FakeSocket):
    def connect(self, _addr) -> None:
        raise OSError("network unreachable")


def test_detect_lan_ip_returns_source_address(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(net.socket, "socket", _FakeSocket)
    assert net.detect_lan_ip() == "192.168.1.42"


def test_detect_lan_ip_falls_back_to_loopback(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(net.socket, "socket", _RaisingSocket)
    assert net.detect_lan_ip() == "127.0.0.1"


def test_detect_lan_ip_closes_the_socket(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    created: list[_FakeSocket] = []

    def _factory(*a, **k) -> _FakeSocket:  # type: ignore[no-untyped-def]
        s = _FakeSocket(*a, **k)
        created.append(s)
        return s

    monkeypatch.setattr(net.socket, "socket", _factory)
    net.detect_lan_ip()
    assert created and created[0].closed is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/discovery/test_net.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'curbcam.discovery.net'`.

- [ ] **Step 3: Write `src/curbcam/discovery/net.py`**

```python
"""Best-effort primary LAN IPv4 detection."""

from __future__ import annotations

import socket


def detect_lan_ip() -> str:
    """Return this host's primary outbound IPv4, or '127.0.0.1' on failure.

    Opens a UDP socket and 'connects' it to a public address. UDP connect
    does not send any packet — it only makes the OS pick the source address
    of the interface that would route there, which we read back. This is the
    standard no-traffic way to learn the primary LAN IP for the startup
    banner + the mDNS A-record.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return str(s.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/discovery/test_net.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/curbcam/discovery/net.py tests/unit/discovery/test_net.py
git commit -m "feat(discovery): detect_lan_ip via UDP-connect source address"
```

---

### Task 3: `MDNSPublisher`

**Files:**
- Create: `src/curbcam/discovery/mdns.py`
- Create: `tests/unit/discovery/test_mdns.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/discovery/test_mdns.py
"""MDNSPublisher builds the right ServiceInfo and registers/unregisters it.
A fake Zeroconf is injected so no multicast happens in the test."""
from __future__ import annotations

import socket

from curbcam.discovery.mdns import MDNSPublisher


class _FakeZeroconf:
    def __init__(self) -> None:
        self.registered: list = []
        self.unregistered: list = []
        self.closed = False

    def register_service(self, info) -> None:  # type: ignore[no-untyped-def]
        self.registered.append(info)

    def unregister_service(self, info) -> None:  # type: ignore[no-untyped-def]
        self.unregistered.append(info)

    def close(self) -> None:
        self.closed = True


def test_start_registers_expected_service() -> None:
    zc = _FakeZeroconf()
    pub = MDNSPublisher("192.168.1.50", 8080, zeroconf=zc)
    pub.start()

    assert len(zc.registered) == 1
    info = zc.registered[0]
    assert info.type == "_http._tcp.local."
    assert info.name == "curbcam._http._tcp.local."
    assert info.server == "curbcam.local."
    assert info.port == 8080
    assert socket.inet_ntoa(info.addresses[0]) == "192.168.1.50"


def test_stop_unregisters_and_closes() -> None:
    zc = _FakeZeroconf()
    pub = MDNSPublisher("10.0.0.5", 8080, zeroconf=zc)
    pub.start()
    info = zc.registered[0]
    pub.stop()

    assert zc.unregistered == [info]
    assert zc.closed is True


def test_stop_is_safe_before_start() -> None:
    zc = _FakeZeroconf()
    pub = MDNSPublisher("10.0.0.5", 8080, zeroconf=zc)
    pub.stop()  # must not raise
    assert zc.unregistered == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/discovery/test_mdns.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'curbcam.discovery.mdns'`.

- [ ] **Step 3: Write `src/curbcam/discovery/mdns.py`**

```python
"""In-process mDNS publisher (spec §3.2).

Advertises curbcam as an `_http._tcp` service with server name
`curbcam.local.`, so `http://curbcam.local:<port>` resolves on the LAN.
Replaces the avahi-in-container approach from the original design (§11.3):
host networking is required for multicast either way, and an in-process
publisher needs no D-Bus daemon and is unit-testable.

The Zeroconf instance is injectable so tests assert the ServiceInfo without
touching the network. In production, start() lazily creates a real one.
"""

from __future__ import annotations

import socket
from typing import Any

from zeroconf import ServiceInfo, Zeroconf

_SERVICE_TYPE = "_http._tcp.local."
_NAME = "curbcam"


class MDNSPublisher:
    def __init__(self, ip: str, port: int, *, zeroconf: Any = None) -> None:
        self._ip = ip
        self._port = port
        self._zc: Any = zeroconf
        self._info: ServiceInfo | None = None

    def _build_info(self) -> ServiceInfo:
        return ServiceInfo(
            _SERVICE_TYPE,
            f"{_NAME}.{_SERVICE_TYPE}",
            addresses=[socket.inet_aton(self._ip)],
            port=self._port,
            server=f"{_NAME}.local.",
        )

    def start(self) -> None:
        if self._zc is None:
            self._zc = Zeroconf()
        self._info = self._build_info()
        self._zc.register_service(self._info)

    def stop(self) -> None:
        if self._zc is None:
            return
        if self._info is not None:
            self._zc.unregister_service(self._info)
            self._info = None
        self._zc.close()
        self._zc = None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/discovery/test_mdns.py -v
```

Expected: 3 passed. (`curbcam.discovery` package import now resolves both submodules.)

- [ ] **Step 5: Commit**

```bash
git add src/curbcam/discovery/mdns.py tests/unit/discovery/test_mdns.py
git commit -m "feat(discovery): MDNSPublisher (python-zeroconf curbcam.local)"
```

---

### Task 4: `/healthz` endpoint + gate exemption

**Files:**
- Create: `src/curbcam/web/routes/health.py`
- Modify: `src/curbcam/web/app.py`
- Modify: `src/curbcam/web/middleware.py`
- Create: `tests/integration/web/test_health.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/web/test_health.py
"""/healthz must answer 200 even on a brand-new, unconfigured install —
the first-run gate must NOT redirect it (the Docker HEALTHCHECK + CI smoke
test depend on this)."""
from fastapi.testclient import TestClient


def test_healthz_ok_on_unconfigured_app(client: TestClient) -> None:
    # The `client` fixture (tests/integration/web/conftest.py) builds an app
    # with no password and no calibration -> the gate is active.
    resp = client.get("/healthz", follow_redirects=False)
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_root_still_redirects_when_unconfigured(client: TestClient) -> None:
    # Sanity: the gate is genuinely active (so the test above proves exemption,
    # not an inactive gate).
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/setup"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/integration/web/test_health.py -v
```

Expected: FAIL — `/healthz` 303-redirects to `/setup` (no route yet + gate not exempt).

- [ ] **Step 3: Write `src/curbcam/web/routes/health.py`**

```python
"""Liveness endpoint for Docker HEALTHCHECK + CI smoke (spec §4).

Unauthenticated and first-run-gate-exempt by design — it must answer before
any setup is done. Reports process liveness only; it does not probe the
camera/pipeline (a detector crash is handled by container restart, §4.3).
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 4: Register the router in `src/curbcam/web/app.py`**

Add `health` to the routes import block (lines 17–27):

```python
from curbcam.web.routes import (
    auth,
    calibration,
    crop,
    debug,
    events,
    health,
    pages,
    settings,
    setup,
    stream,
)
```

And add the include alongside the others (after `app.include_router(debug.router)`):

```python
    app.include_router(health.router)
```

- [ ] **Step 5: Exempt `/healthz` from the first-run gate in `src/curbcam/web/middleware.py`**

Add `"/healthz"` to the `_EXEMPT_PREFIXES` tuple:

```python
_EXEMPT_PREFIXES = (
    "/setup",
    "/api/setup",
    "/api/auth/login",
    "/api/calibration",
    "/api/crop",
    "/static",
    "/healthz",
)
```

- [ ] **Step 6: Run test to verify it passes**

```bash
uv run pytest tests/integration/web/test_health.py -v
```

Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add src/curbcam/web/routes/health.py src/curbcam/web/app.py src/curbcam/web/middleware.py tests/integration/web/test_health.py
git commit -m "feat(web): /healthz endpoint, exempt from first-run gate"
```

---

## Slice B — serve wiring + db upgrade

### Task 5: `serve` mDNS lifecycle + startup banner

**Files:**
- Modify: `src/curbcam/cli.py`
- Create: `tests/integration/test_cli_serve_mdns.py`

The change is additive: `create_app` is untouched (stays pure); mDNS lives only in the `serve` command path (spec §5).

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_cli_serve_mdns.py
"""serve must start/stop the mDNS publisher around uvicorn and print the
banner when mDNS is enabled, and skip the publisher entirely with --no-mdns.
uvicorn.run is patched so no socket is bound."""
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import curbcam.cli as cli_mod
from curbcam.cli import app

runner = CliRunner()


class _FakePublisher:
    instances: list["_FakePublisher"] = []

    def __init__(self, ip: str, port: int) -> None:
        self.ip = ip
        self.port = port
        self.started = 0
        self.stopped = 0
        _FakePublisher.instances.append(self)

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1


def _patch(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _FakePublisher.instances.clear()
    monkeypatch.setattr(cli_mod.uvicorn, "run", lambda *a, **k: None)
    monkeypatch.setattr(cli_mod, "MDNSPublisher", _FakePublisher)
    monkeypatch.setattr(cli_mod, "detect_lan_ip", lambda: "10.0.0.5")


def test_serve_starts_and_stops_publisher_and_prints_banner(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _patch(monkeypatch)
    result = runner.invoke(
        app,
        ["serve", "--port", "8080", "--config", str(tmp_path / "c.yaml"),
         "--data-dir", str(tmp_path / "data"), "--media-dir", str(tmp_path / "media")],
    )
    assert result.exit_code == 0, result.output
    assert len(_FakePublisher.instances) == 1
    pub = _FakePublisher.instances[0]
    assert pub.started == 1 and pub.stopped == 1
    assert pub.ip == "10.0.0.5" and pub.port == 8080
    assert "curbcam.local:8080" in result.output
    assert "10.0.0.5:8080" in result.output


def test_serve_no_mdns_skips_publisher(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _patch(monkeypatch)
    result = runner.invoke(
        app,
        ["serve", "--no-mdns", "--config", str(tmp_path / "c.yaml"),
         "--data-dir", str(tmp_path / "data"), "--media-dir", str(tmp_path / "media")],
    )
    assert result.exit_code == 0, result.output
    assert _FakePublisher.instances == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/integration/test_cli_serve_mdns.py -v
```

Expected: FAIL — `cli` has no `MDNSPublisher`/`detect_lan_ip` attribute; `--mdns/--no-mdns` not defined.

- [ ] **Step 3: Add imports to `src/curbcam/cli.py`**

After the existing `from curbcam.config.store import ConfigStore` import block (near the top, with the other `from curbcam...` imports), add:

```python
from curbcam.discovery.mdns import MDNSPublisher
from curbcam.discovery.net import detect_lan_ip
```

- [ ] **Step 4: Rewrite the `serve` command body in `src/curbcam/cli.py`**

Add the `mdns` option to the signature and wrap `uvicorn.run` with the publisher lifecycle. Replace the existing `serve` function (lines 100–124) with:

```python
@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind address"),
    port: int = typer.Option(8000, help="Bind port"),
    config: Path = typer.Option(Path("curbcam.yaml"), help="Path to YAML config"),
    data_dir: Path = typer.Option(Path("./data"), help="Directory for SQLite DB"),
    media_dir: Path = typer.Option(Path("./media"), help="Directory for event JPEGs"),
    mdns: bool = typer.Option(True, "--mdns/--no-mdns", help="Advertise curbcam.local via mDNS"),
) -> None:
    """Run the web app: detector pipeline + UI in one process."""
    store = ConfigStore(config)
    settings = store.load()
    _setup_logging(settings.server.log_level)

    db = Database.for_sqlite_path(data_dir / "curbcam.sqlite")
    ensure_schema(db)

    supervisor = Supervisor(
        config_store=store,
        db=db,
        bus=EventBus(),
        media_root=media_dir,
        auth_store=AuthStore(data_dir / "auth.json"),
    )
    app_obj = create_app(supervisor)

    publisher: MDNSPublisher | None = None
    if mdns:
        ip = detect_lan_ip()
        publisher = MDNSPublisher(ip, port)
        publisher.start()
        typer.echo(f"Open http://curbcam.local:{port}   (or http://{ip}:{port})")

    try:
        uvicorn.run(app_obj, host=host, port=port)
    finally:
        if publisher is not None:
            publisher.stop()
```

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/integration/test_cli_serve_mdns.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/curbcam/cli.py tests/integration/test_cli_serve_mdns.py
git commit -m "feat(cli): serve advertises curbcam.local via mDNS + startup banner"
```

---

### Task 6: `curbcam db upgrade` (real Alembic migration)

**Files:**
- Modify: `src/curbcam/cli.py`
- Create: `tests/integration/test_cli_db_upgrade.py`

This is the migrate-on-boot mechanism (spec §6). `ensure_schema` is bootstrap-only and will NOT migrate an existing DB; `db upgrade` runs `alembic upgrade head` against the `--data-dir` SQLite, overriding `alembic.ini`'s relative URL so `--data-dir` is the single source of truth.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_cli_db_upgrade.py
"""`db upgrade` runs alembic against the --data-dir sqlite and leaves it at
head. Runs from the repo root so alembic.ini + migrations/ resolve."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from curbcam.cli import app
from curbcam.storage.db import LATEST_MIGRATION_REVISION

runner = CliRunner()


def test_db_upgrade_brings_fresh_db_to_head(tmp_path: Path) -> None:
    result = runner.invoke(app, ["db", "upgrade", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output

    db_path = tmp_path / "curbcam.sqlite"
    assert db_path.exists()
    con = sqlite3.connect(db_path)
    try:
        ver = con.execute("SELECT version_num FROM alembic_version").fetchone()
        tables = {
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        con.close()

    assert ver is not None and ver[0] == LATEST_MIGRATION_REVISION
    assert {"events", "calibrations"} <= tables


def test_db_upgrade_is_idempotent(tmp_path: Path) -> None:
    first = runner.invoke(app, ["db", "upgrade", "--data-dir", str(tmp_path)])
    second = runner.invoke(app, ["db", "upgrade", "--data-dir", str(tmp_path)])
    assert first.exit_code == 0 and second.exit_code == 0, second.output
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/integration/test_cli_db_upgrade.py -v
```

Expected: FAIL — `db` has no `upgrade` command.

- [ ] **Step 3: Add the `db upgrade` command to `src/curbcam/cli.py`**

Add an Alembic import near the top imports:

```python
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
```

Then add this command in the `db` sub-app, after the existing `db_init` function:

```python
@db_app.command("upgrade")
def db_upgrade(data_dir: Path = typer.Option(Path("./data"))) -> None:
    """Run all pending Alembic migrations against the data-dir database.

    Used by the container entrypoint on every boot so `docker compose pull`
    of a newer image migrates an existing install to head (spec §6).
    `alembic.ini`'s relative sqlalchemy.url is overridden so --data-dir is
    the single source of truth for the DB location.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "curbcam.sqlite"
    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    alembic_command.upgrade(cfg, "head")
    typer.echo(f"Database at {db_path} upgraded to head.")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/integration/test_cli_db_upgrade.py -v
```

Expected: 2 passed. (Alembic logs migration output; the command exits 0.)

- [ ] **Step 5: Run the full suite to confirm no regressions**

```bash
uv run pytest -q
```

Expected: all green (MVP-1/MVP-2 suites + the new discovery/health/serve/db-upgrade tests).

- [ ] **Step 6: Commit**

```bash
git add src/curbcam/cli.py tests/integration/test_cli_db_upgrade.py
git commit -m "feat(cli): db upgrade runs alembic head against --data-dir"
```

---

## Slice C — Container artifacts

> Slice C produces files but no Python unit tests; correctness is proven by the CI smoke job (Slice D / Task 11) and the documented manual Pi run. If Docker is available locally, the optional local build/run at the end of Task 9 is the fastest feedback loop.

### Task 7: `.dockerignore` + `.env.example`

**Files:**
- Create: `.dockerignore`
- Create: `.env.example`

- [ ] **Step 1: Write `.dockerignore`**

```gitignore
# Keep the build context small + deterministic.
.git
.venv
venv
env
__pycache__
*.py[cod]
.pytest_cache
.ruff_cache
.mypy_cache
.coverage
htmlcov
# Runtime data is mounted at runtime, never baked into the image.
data
media
*.sqlite
*.sqlite-journal
# Local + ephemeral
.env
.env.local
.codex-review-*.txt
.opencode-review-*.txt
.coplan-*.md
.pr-review-out
# Not needed in the image.
docs
tests
```

- [ ] **Step 2: Write `.env.example`**

```bash
# Copy to .env (gitignored) and uncomment what you need.
# curbcam reads CURBCAM_*-prefixed env vars; nested keys use __ (double underscore).

# Keep RTSP credentials out of curbcam.yaml by setting the camera source here:
# CURBCAM_CAMERA__SOURCE=rtsp://user:password@camera.local:554/stream

# Local timezone (affects log timestamps only; the UI renders in the browser TZ):
# TZ=America/Los_Angeles
```

- [ ] **Step 3: Commit**

```bash
git add .dockerignore .env.example
git commit -m "build(docker): .dockerignore + .env.example"
```

---

### Task 8: `docker-entrypoint.sh`

**Files:**
- Create: `docker-entrypoint.sh`

- [ ] **Step 1: Write `docker-entrypoint.sh`**

```sh
#!/bin/sh
# Migrate-before-serve (spec §6): every container start brings the mounted
# /data DB to head, so `docker compose pull` of a newer image upgrades an
# existing install. Then hand off to the web app. Args after the script
# (e.g. --no-mdns) are forwarded to `serve`.
set -e

curbcam db upgrade --data-dir /data

exec curbcam serve \
    --host 0.0.0.0 \
    --port 8080 \
    --data-dir /data \
    --media-dir /media \
    --config /data/curbcam.yaml \
    "$@"
```

- [ ] **Step 2: Mark it executable (so the `chmod` in the Dockerfile is belt-and-suspenders)**

```bash
git update-index --chmod=+x docker-entrypoint.sh 2>/dev/null || chmod +x docker-entrypoint.sh
```

- [ ] **Step 3: Commit**

```bash
git add docker-entrypoint.sh
git commit -m "build(docker): migrate-before-serve entrypoint"
```

---

### Task 9: `Dockerfile`

**Files:**
- Create: `Dockerfile`

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1

# ---- builder: produce a wheel ----
FROM python:3.12-slim-bookworm AS builder
RUN pip install --no-cache-dir uv
WORKDIR /build
# Copy only what the build backend (hatchling) needs to produce the wheel.
COPY pyproject.toml README.md ./
COPY src ./src
RUN uv build --wheel --out-dir /wheels

# ---- runtime ----
FROM python:3.12-slim-bookworm AS runtime
# OpenCV (headless) needs libglib2.0-0; libgomp1 backs numpy/opencv threading.
# tini reaps zombies + forwards signals (compose also sets init: true).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 tini \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv

# Install curbcam into the SYSTEM python (no venv) from the built wheel.
# The [picamera2] extra is deliberately NOT installed — Pi Camera Module
# support in Docker is deferred (spec §2.2). USB/RTSP/file work here.
COPY --from=builder /wheels/*.whl /tmp/wheels/
RUN uv pip install --system --no-cache /tmp/wheels/*.whl && rm -rf /tmp/wheels

# Alembic config + migration scripts live at the repo root (outside the wheel),
# so copy them in — `curbcam db upgrade` needs them at runtime.
WORKDIR /app
COPY alembic.ini ./
COPY migrations ./migrations
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/healthz').status == 200 else 1)"

# Runs as root: single-purpose appliance, zero-fuss camera device access (spec §7.1).
ENTRYPOINT ["tini", "--", "/docker-entrypoint.sh"]
```

- [ ] **Step 2 (optional, if Docker is available locally): build + run the image**

```bash
docker build -t curbcam:dev .
mkdir -p _smoke/data _smoke/media _smoke/frames
docker run -d --name curbcam-dev -p 8080:8080 \
    -v "$PWD/_smoke/data:/data" -v "$PWD/_smoke/media:/media" -v "$PWD/_smoke/frames:/frames" \
    -e CURBCAM_CAMERA__SOURCE=file:/frames \
    curbcam:dev --no-mdns
sleep 8
curl -fsS http://localhost:8080/healthz   # -> {"status":"ok"}
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/   # -> 303
docker rm -f curbcam-dev && rm -rf _smoke
```

Expected: `/healthz` returns `{"status":"ok"}`, `/` returns `303`. (If `uv build` or an import fails, fix before committing — this is the same path CI exercises.)

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "build(docker): multi-stage image (root, no-picamera2, migrate-on-boot)"
```

---

### Task 10: `docker-compose.yml`

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Write `docker-compose.yml`**

```yaml
services:
  curbcam:
    image: ghcr.io/patientvibes/curbcam:latest
    restart: unless-stopped
    # REQUIRED: mDNS multicast (curbcam.local) cannot cross the Docker bridge
    # NAT, so the container shares the host network. Host networking also
    # publishes port 8080 directly — there is intentionally no `ports:` block.
    network_mode: host
    init: true
    volumes:
      - ./data:/data            # curbcam.yaml, curbcam.sqlite, auth.json
      - ./media:/media          # event images + thumbnails
      - /run/udev:/run/udev:ro
    devices:
      - /dev/video0:/dev/video0 # USB / V4L2 camera
      # Pi Camera Module (picamera2) in Docker is a future slice (spec §2.2);
      # /dev/dma_heap would be mounted here once it lands. For now use a USB
      # or RTSP camera, or run curbcam natively for the Pi Camera Module.
    env_file:
      - .env                    # optional; see .env.example
    environment:
      - TZ=America/Los_Angeles  # log timestamps only
```

- [ ] **Step 2: Validate the compose file (if Docker Compose is available)**

```bash
docker compose config -q && echo "compose OK"
```

Expected: `compose OK` (no schema errors). If Docker isn't installed locally, skip — CI and the manual Pi run cover it.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "build(docker): docker-compose.yml (host net, USB cam, GHCR image)"
```

---

## Slice D — CI/CD

### Task 11: `docker.yml` — amd64 build+smoke on PR, multi-arch→GHCR on tag

**Files:**
- Create: `.github/workflows/docker.yml`

- [ ] **Step 1: Write `.github/workflows/docker.yml`**

```yaml
name: docker

on:
  push:
    branches: [main]
    tags: ["v*"]
  pull_request:

concurrency:
  group: docker-${{ github.ref }}
  cancel-in-progress: true

jobs:
  build-smoke:
    name: build amd64 + smoke
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: docker/setup-buildx-action@v3

      - name: Build amd64 image (load locally)
        uses: docker/build-push-action@v6
        with:
          context: .
          load: true
          tags: curbcam:smoke
          platforms: linux/amd64

      - name: Smoke test the image
        run: |
          set -euo pipefail
          mkdir -p smoke/data smoke/media smoke/frames
          docker run -d --name curbcam-smoke \
            -p 8080:8080 \
            -v "$PWD/smoke/data:/data" \
            -v "$PWD/smoke/media:/media" \
            -v "$PWD/smoke/frames:/frames" \
            -e CURBCAM_CAMERA__SOURCE=file:/frames \
            curbcam:smoke --no-mdns

          ok=0
          for _ in $(seq 1 30); do
            if curl -fsS http://localhost:8080/healthz >/dev/null; then ok=1; break; fi
            sleep 1
          done
          if [ "$ok" != "1" ]; then echo "healthz never came up"; docker logs curbcam-smoke; exit 1; fi

          echo "healthz OK"
          code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/)
          if [ "$code" != "303" ]; then echo "expected / -> 303, got $code"; docker logs curbcam-smoke; exit 1; fi
          echo "root redirect OK ($code)"

          # The entrypoint must have migrated the DB to head before serving.
          if [ ! -f smoke/data/curbcam.sqlite ]; then echo "db upgrade did not create the sqlite"; docker logs curbcam-smoke; exit 1; fi
          echo "db migrated OK"

          docker logs curbcam-smoke
          docker rm -f curbcam-smoke

  release:
    name: multi-arch release -> GHCR
    if: startsWith(github.ref, 'refs/tags/v')
    needs: build-smoke
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      - uses: docker/setup-qemu-action@v3

      - uses: docker/setup-buildx-action@v3

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Image metadata (tags + labels)
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/patientvibes/curbcam
          tags: |
            type=raw,value=latest
            type=semver,pattern=v{{version}}

      - name: Build + push multi-arch
        uses: docker/build-push-action@v6
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

- [ ] **Step 2: Validate the workflow YAML locally**

```bash
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/docker.yml')); print('yaml OK')"
```

Expected: `yaml OK`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/docker.yml
git commit -m "ci(docker): amd64 build+smoke on PR, multi-arch GHCR push on v* tags"
```

- [ ] **Step 4: Push the branch and open the PR to exercise `build-smoke` in real CI**

```bash
git push -u origin docs/mvp-3-docker-install
```

Then open a PR (e.g. `gh pr create --fill`). Confirm the `docker / build amd64 + smoke` check goes green. The `release` job is tag-gated and will not run on the PR. (First GHCR publish on the eventual tag may need the package's visibility set in repo/org settings — spec §10.)

---

## Slice E — Docs + finalize

### Task 12: README rewrite, design-spec sync, gates, tag

**Files:**
- Modify: `README.md`
- Modify: `docs/specs/2026-05-28-curbcam-design.md`

- [ ] **Step 1: Update `README.md` — install + status**

Replace the "Status" line (line 9–10) to mark MVP-3, and replace the MVP-1 "Install" block (the `git clone … uv pip install` fenced block, lines 16–33) with the Docker quick-start:

```markdown
## Install (Docker)

```bash
mkdir curbcam && cd curbcam
curl -O https://raw.githubusercontent.com/PatientVibes/curbcam/main/docker-compose.yml
docker compose up -d
# then browse to http://curbcam.local:8080
```

Three commands. The image is multi-arch (Raspberry Pi arm64 + x86 amd64) and
published to GHCR. On first launch every page redirects to the setup wizard
(password → privacy notice → camera → align → calibrate).

**Updating:** `docker compose pull && docker compose up -d`. The container runs
database migrations automatically on boot, so upgrades are safe.

**Cameras in Docker:** USB (`usb:0`), RTSP (`rtsp://…`), and file replay are
supported. The Raspberry Pi Camera Module (picamera2) is not yet supported
inside the Docker image — use a USB camera, or run curbcam natively, until that
lands. Keep RTSP credentials in a gitignored `.env` (see `.env.example`) rather
than in `curbcam.yaml`.
```

Keep the existing "Run the web app", "Camera sources", "Before you install", and
"Inspiration" sections, but update any `:8000` references in the Docker context
to `:8080`, and change the "Inspiration" line that says the Docker path is
"(MVP-3)" to reflect that it has shipped.

- [ ] **Step 2: Update the dev-from-source note**

Under a new "Develop from source" subsection (so the `git clone`/`uv` flow isn't lost), keep:

```markdown
## Develop from source

```bash
git clone https://github.com/PatientVibes/curbcam
cd curbcam
uv venv && uv pip install -e ".[dev]"
uv run curbcam serve            # http://localhost:8000  (mDNS on; --no-mdns to disable)
```
```

- [ ] **Step 3: Sync `docs/specs/2026-05-28-curbcam-design.md`**

Three edits so the original design spec stops contradicting reality:

1. §11.1 (Docker Compose block, ~lines 445–462): drop `ports: ["8080:8080"]`, add `network_mode: host` and `init: true`, and add the explanatory comment that host networking is required for mDNS and publishes 8080 directly. Change the device list comment to note `/dev/dma_heap` / picamera2 is a future slice.

2. §11.3 (Discovery, ~lines 474–477): replace "The container runs avahi and advertises itself as `curbcam.local`" with the in-process `python-zeroconf` approach (host networking required; no avahi/D-Bus). Keep the IP-in-logs fallback line.

3. §13.2 (Deferred) and §14 (Risks): add a line that picamera2-in-Docker is deferred (Debian Bookworm apt `python3-picamera2` targets Python 3.11 vs the 3.12 base image; supported container cameras are USB/RTSP/file; picamera2 remains native-only). Reference the MVP-3 spec §2.2.

- [ ] **Step 4: Run the full gate suite**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/curbcam
uv run pytest -q
```

Expected: all clean/green. Fix any lint/format/type issues inline (e.g. run `uv run ruff format .` if the format check fails).

- [ ] **Step 5: Commit**

```bash
git add README.md docs/specs/2026-05-28-curbcam-design.md
git commit -m "docs: MVP-3 Docker install path — README + design-spec sync"
```

- [ ] **Step 6: Tag a release once the PR is merged to main (cuts the first GHCR image)**

After the PR merges to `main`:

```bash
git checkout main
git pull
git tag v0.1.0
git push origin v0.1.0
```

Expected: the `release` job in `docker.yml` builds `linux/amd64,linux/arm64` and
pushes `ghcr.io/patientvibes/curbcam:latest` + `:v0.1.0`. Verify the package
page shows a multi-arch manifest with both platforms.

- [ ] **Step 7: Manual verification on a Pi (documented; not CI)**

On a Raspberry Pi (Bookworm) with Docker + a USB camera:

```bash
mkdir curbcam && cd curbcam
curl -O https://raw.githubusercontent.com/PatientVibes/curbcam/main/docker-compose.yml
docker compose up -d
# browse to http://curbcam.local:8080 from another machine on the LAN
```

Expected: `curbcam.local` resolves, the first-run wizard appears, and the
calibration wizard completes against the USB camera. This closes the
picamera2-deferral / hardware gap that CI cannot cover.

---

## Notes for the implementer

- **Do not touch `create_app`'s purity.** mDNS belongs only in `serve` (Task 5). If a test in `tests/integration/web/` starts hitting the network, you broke this invariant.
- **`db upgrade` resolves `alembic.ini` from the current working directory** — the repo root in tests, `/app` in the container (the Dockerfile sets `WORKDIR /app` and copies `alembic.ini` + `migrations/` there). If you change the WORKDIR, update the entrypoint accordingly.
- **`LATEST_MIGRATION_REVISION`** in `src/curbcam/storage/db.py` must already equal the head revision; Task 6's test asserts against it. If a new migration lands later, that constant and the test move together.
- **GHCR image names are lowercase** — `ghcr.io/patientvibes/curbcam`, not `PatientVibes`.
```

## Self-Review

**Spec coverage:** §2.1 in-scope items → discovery (T2–3), `/healthz` (T4), serve+mDNS (T5), `db upgrade` (T6), Dockerfile/compose/entrypoint/dockerignore/env (T7–10), CI build+smoke+release (T11), README+spec-sync (T12). §2.2 deferral → reflected in Dockerfile (no picamera2 extra), compose comment, README, spec-sync. §3 discovery, §4 health, §5 serve invariant, §6 migrate-on-boot, §7 container, §8 CI, §9 docs, §11 verification all map to tasks. No gaps.

**Placeholders:** none — every code/edit step shows full content and exact commands.

**Type/name consistency:** `MDNSPublisher(ip, port, *, zeroconf=None)` + `.start()`/`.stop()` used identically in T3, T5, and the entrypoint forwarding `--no-mdns`. `detect_lan_ip()` signature consistent T2/T5. `db upgrade` / `--data-dir` / `LATEST_MIGRATION_REVISION` consistent T6 and entrypoint T8. `/healthz` + `_EXEMPT_PREFIXES` consistent T4 and smoke T11.

This plan is on branch `docs/mvp-3-docker-install` (the spec is already committed there).

