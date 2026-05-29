# curbcam MVP-3 — Docker / mDNS / Install Path — Design Spec

- **Date:** 2026-05-29
- **Status:** Approved (co-planned with Gemini 2.5 Pro; 2 review passes)
- **Owner:** PatientVibes
- **Implements:** overall design spec §11 (Install & Deployment), §13.1 deployment
  line items. Read alongside `docs/specs/2026-05-28-curbcam-design.md` (cited §N).

## 1. Background & Goal

MVP-1 (detector, four camera sources, storage, CLI) and MVP-2 (the full FastAPI
web app — dashboard, live MJPEG, SSE, wizards, auth) are built and merged. What
remains from the original design is the thing that makes curbcam *installable* by
its target audience: a single Docker-based deployment path with zero-config
discovery.

**Goal:** a non-technical Raspberry Pi owner goes from a Pi with Docker to a
running, reachable speed camera at `http://curbcam.local:8080` in three commands,
and upgrades later with `docker compose pull && docker compose up -d` — with a
multi-arch (arm64 + amd64) image published to GHCR by a tagged-release pipeline.

This is the design spec's §2 goal #1 ("under 15 minutes, zero shell commands
beyond the install") and #4 ("reproducible on any laptop via Docker") made real.

## 2. Scope

### 2.1 In MVP-3
- `src/curbcam/discovery/` — LAN-IP detection + an in-process mDNS publisher.
- `GET /healthz` — unauthenticated, first-run-gate-exempt liveness endpoint.
- `serve` wiring: mDNS lifecycle + a human-readable startup banner.
- `curbcam db upgrade` — runs real Alembic migrations (the update path depends
  on this; see §6).
- Container artifacts: `Dockerfile` (multi-arch), `docker-compose.yml`,
  `docker-entrypoint.sh`, `.dockerignore`, `.env.example`.
- CI/CD: a `docker.yml` workflow — amd64 build + smoke on every PR; multi-arch
  build + push to GHCR on `v*` tags.
- Docs: README rewrite + design-spec sync.

### 2.2 Deferred (with rationale)
> **Update (2026-05-29):** picamera2-in-Docker is **no longer deferred** — it ships as a dedicated
> arm64 `:picamera` image (Debian Trixie / Python 3.13), hardware-validated on a Pi. See
> `docs/specs/2026-05-29-curbcam-picamera2-docker.md`. The rationale below records why MVP-3 itself
> deferred it.

- **picamera2 (Pi Camera Module) inside Docker.** This is the design spec's §14
  "riskiest assembly," and it is genuinely unviable on the chosen base image:
  Debian Bookworm's apt `python3-picamera2` is compiled against the system
  **Python 3.11**, while `python:3.12-slim-bookworm` is **CPython 3.12** — the
  C extensions will not import. The packages also live in the Raspberry Pi
  Foundation apt repo, not Debian's. Solving Pi-Camera-in-a-3.12-container
  (pip `rpi-libcamera` wheels, or a non-standard base) is a packaging research
  task that cannot be verified in CI without Pi hardware. It is deferred to its
  own follow-up slice so it does not block a shippable Docker image.

  **Consequence:** the *supported* in-container camera sources are **USB, RTSP,
  and file**. The picamera2 source code (`camera/picamera2_source.py`) and the
  `[picamera2]` pip extra remain in the repo for **native** (non-Docker) installs
  on a Pi. Pi-Camera-Module users either run natively or use a USB camera until
  the follow-up lands.
- Pre-flashed SD image (pi-gen), Watchtower auto-update, Home Assistant add-on,
  alerts — unchanged from design spec §13.2.

### 2.3 Non-goals
- No new runtime services or processes (single-process / single-container model,
  §4.3 holds).
- No change to MVP-1/MVP-2 behavior or public surfaces.

## 3. Discovery module — `src/curbcam/discovery/`

A pure, hardware-free, unit-testable package. Kept **out of `web/`** because
discovery is a process/deployment concern, not a request concern. It is
orchestrated by the CLI (the appropriate layer per §4.2), never imported by
`web/`.

### 3.1 `net.py`

```python
def detect_lan_ip() -> str:
    """Best-effort primary LAN IPv4. Opens a UDP socket 'connected' to a
    public address (no packet is sent) and reads the chosen source address.
    Returns '127.0.0.1' if detection fails."""
```

Unit-tested by monkeypatching the socket so no real network is touched.

### 3.2 `mdns.py`

```python
class MDNSPublisher:
    def __init__(self, ip: str, port: int, *, zeroconf: Zeroconf | None = None): ...
    def start(self) -> None: ...   # register the service
    def stop(self) -> None: ...    # unregister + close
```

`start()` registers an `_http._tcp.local.` service named `curbcam`, with
`server="curbcam.local."`, the supplied IP, and port. The `Zeroconf` instance and
IP are injectable so the unit test asserts the built `ServiceInfo` fields
(name, server, addresses, port) **without** registering on the network.

**Why zeroconf, not avahi (revises §11.3):** running avahi inside the container
needs a D-Bus socket mount and host networking, and is awkward to test. mDNS
multicast cannot cross the Docker bridge NAT regardless, so host networking is
required either way — at which point an in-process `python-zeroconf` publisher is
strictly simpler, has no extra runtime daemon, and is unit-testable. New
dependency: `zeroconf>=0.132`.

## 4. Health endpoint

`GET /healthz` → `{"status": "ok"}`, unauthenticated, defined in
`web/routes/health.py` and registered in `web/app.py`. It **must** be added to
the first-run gate's `_EXEMPT_PREFIXES` in `web/middleware.py`; otherwise the
gate 303-redirects it to `/setup`, which would break both the Docker `HEALTHCHECK`
and the CI smoke test. Verified by an integration test that hits `/healthz` on a
fully-unconfigured app and asserts 200.

## 5. `serve` wiring & startup banner

`serve` (in `cli.py`) gains `--mdns / --no-mdns` (default on). When mDNS is on,
it constructs `MDNSPublisher(detect_lan_ip(), port)`, calls `start()` before
`uvicorn.run(...)`, and `stop()` in a `finally`. It prints:

```
Open http://curbcam.local:<port>   (or http://<detected-ip>:<port>)
```

**Critical invariant (preserves §4.2 / MVP-2 test contract):** mDNS is started
**only in the `serve` CLI path**, never inside `create_app`. `create_app` must
remain a pure function with no network side effects — every MVP-2 integration
test relies on this. The `serve` local-dev default port stays **8000**; the
container overrides to **8080** via the entrypoint (§7).

## 6. Migrations on update — `curbcam db upgrade`

`ensure_schema` (db.py) is **bootstrap-only**: it `create_all`s the current
models and stamps the latest revision on a *fresh* database. It does **not** run
`alembic upgrade` on an *existing* one. So a user who `docker compose pull`s a
newer image with a schema change would silently **not** be migrated — the
documented update path would be a data-corruption trap.

MVP-3 adds a `curbcam db upgrade` subcommand that programmatically runs
`alembic.command.upgrade(cfg, "head")`, overriding `sqlalchemy.url` via
`cfg.set_main_option(...)` so the `--data-dir` is the single source of truth for
the DB location (the existing `migrations/env.py` supports this unmodified, for
both online and offline modes). The container entrypoint runs `db upgrade`
**before** `serve`, so every container start migrates an existing install to
head. Running the bootstrap `ensure_schema` afterward is a verified no-op
(idempotent: `create_all` does not alter existing tables; the version stamp is
guarded by `IF NOT EXISTS` + a presence check).

## 7. Container artifacts

### 7.1 `Dockerfile`

Multi-stage on `python:3.12-slim-bookworm` (Bookworm matches Pi OS):

- **builder stage** builds a wheel from the project.
- **runtime stage** `uv pip install --system <wheel>` (no venv — keeps the door
  open for a future system-level picamera2; the `[picamera2]` extra is **not**
  installed). Runtime apt: `libglib2.0-0` (OpenCV), `tini`. **No
  picamera2/libcamera layer** (§2.2). Copies `alembic.ini` + `migrations/` into
  the image (needed by `db upgrade`). Runs as **root** (single-purpose
  appliance — zero-fuss device access, no `group_add`/cgroup tuning).
- `HEALTHCHECK` runs a `python -c` urllib request against
  `http://localhost:8080/healthz`.
- `ENTRYPOINT ["tini", "--", "/docker-entrypoint.sh"]`.

### 7.2 `docker-entrypoint.sh`

```sh
#!/bin/sh
set -e
curbcam db upgrade --data-dir /data
exec curbcam serve --host 0.0.0.0 --port 8080 \
     --data-dir /data --media-dir /media --config /data/curbcam.yaml "$@"
```

Migrate-before-serve is the point (§6).

### 7.3 `docker-compose.yml` (the downloaded artifact)

```yaml
services:
  curbcam:
    image: ghcr.io/PatientVibes/curbcam:latest
    restart: unless-stopped
    network_mode: host          # REQUIRED: mDNS multicast can't cross bridge NAT.
    init: true
    # No `ports:` — host networking publishes 8080 directly.
    volumes:
      - ./data:/data            # YAML, sqlite, auth.json
      - ./media:/media          # event images + thumbs
      - /run/udev:/run/udev:ro
    devices:
      - /dev/video0:/dev/video0 # USB camera
      # /dev/dma_heap + picamera2 (Pi Camera Module) are a future slice — see spec §2.2.
    env_file:
      - .env                    # CURBCAM_CAMERA__SOURCE=rtsp://user:pw@... etc.
    environment:
      - TZ=America/Los_Angeles
```

### 7.4 `.dockerignore` & `.env.example`

`.dockerignore` excludes `.venv`, caches, `.codex-review-*.txt`, `.coplan-*.md`,
`data/`, `media/`, `docs/`, `tests/`, `.git`. `.env.example` is a committed
template (commented `CURBCAM_CAMERA__SOURCE`, `TZ`) — the gitignored `.env`
pattern from §11.1.

## 8. CI/CD — `.github/workflows/docker.yml`

The existing `ci.yml` gates job (lint/type/test) is untouched.

- **PR + push-to-main:** `docker/setup-buildx-action`, build the **amd64** image
  (`load`, no push), `docker run` it with a baked fixture directory and
  `CURBCAM_CAMERA__SOURCE=file:...`, then assert: `/healthz` → 200, `/` → 303
  to `/setup`, and the entrypoint's `db upgrade` produced a DB at head. Catches
  image-packaging breakage on every PR. (Implemented as an inline shell step or
  a `tests/docker/test_image_smoke.py` marked `docker`, excluded from the default
  pytest run like `e2e`.)
- **Tag `v*`:** `docker/setup-qemu-action` + buildx multi-arch (amd64 + arm64),
  `docker/login-action` → GHCR, push `:latest` + `:vX.Y.Z`.
  `permissions: { contents: read, packages: write }`.

## 9. Docs

- **README:** replace the dev-only install with the 3-command Docker install,
  port 8080, `curbcam.local`, the (now truthful) `docker compose pull` update
  path, supported Docker camera sources = USB/RTSP/file (Pi-Cam → native or USB
  for now), mark MVP-3 done.
- **Design spec sync** (`2026-05-28-curbcam-design.md`): §11.3 avahi → zeroconf;
  §11.1 drop `ports:` / add `network_mode: host`; note picamera2-in-Docker
  deferral in §11 / §13.2 / §14.

## 10. Risks

- **mDNS requires host networking** — a hard, documented requirement of the
  compose file.
- **`db upgrade` url wiring** — `alembic.ini` ships a relative
  `sqlalchemy.url`; the command overrides it to the resolved `--data-dir` path.
  Verify migrations hit `/data/curbcam.sqlite`, not a stray relative path.
  (Gemini-verified the override mechanism against `migrations/env.py`.)
- **GHCR first publish** — package visibility may need a one-time settings tweak.
- **arm64 build time** — QEMU emulation is slow, but only runs on tags.
- **picamera2-in-Docker** — explicitly deferred (§2.2); no longer an MVP-3 risk.

## 11. Verification

- `uv run pytest -q` green: unit (`detect_lan_ip`, `MDNSPublisher` ServiceInfo,
  `db upgrade`), integration (gate-exempt `/healthz`, `serve` mDNS wiring).
- `ruff check`, `ruff format --check`, `mypy src/curbcam` clean.
- CI amd64 smoke: image boots, entrypoint migrates, `/healthz` 200, `/` 303.
- Tag `v0.1.0` → GHCR shows a multi-arch manifest (amd64 + arm64).
- **Manual (documented, not CI):** `docker compose up -d` on a Pi with a USB
  camera; browse `http://curbcam.local:8080`; complete the first-run wizard.

## 12. Open Questions

None at design time. The picamera2-in-Docker follow-up will need its own spec
(base-image / libcamera-packaging investigation).
