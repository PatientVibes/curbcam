# curbcam — Design Spec

- **Date:** 2026-05-28
- **Status:** Draft, pending user review
- **Owner:** PatientVibes
- **Inspired by:** [pageauc/speed-camera](https://github.com/pageauc/speed-camera) — re-implemented from scratch, zero shared code

## 1. Background

`pageauc/speed-camera` is a 2000-line single-file Python script that detects
moving objects via OpenCV, calculates their speed from frame-to-frame pixel
displacement against a manually-measured calibration, and exposes the results
through a directory-listing web server. It works, and has worked for years,
but the user-facing experience has serious friction:

- Installation is `curl | bash` onto a hand-prepared Pi, with frequent
  OS-version-specific stumbles (e.g. `rpicam` ↔ `libcamera` symlinks on recent
  Raspberry Pi OS releases).
- Calibration requires the user to enable a flag, capture an image, count
  pixels with an external ruler tool, compute mm/px by hand, SSH back in,
  edit a 200-line Python config in `nano`, and restart. This is the cliff
  most non-technical users fall off.
- Settings live in `config.py` with ~50 knobs and no UI; `from config import *`
  patterns make the code hard to refactor.
- The web server is a directory lister, not a dashboard — no live preview,
  no live event feed, no notion of "currently tracking."
- No real authentication, no API contract, no migration story for the
  SQLite schema, no automated tests.

`curbcam` is a complete re-implementation targeting the same hardware
(Raspberry Pi + Pi/USB/RTSP camera) and the same core algorithm (frame-diff
contour detection + pixel-to-mm calibration), but with a modern stack,
sharply-bounded modules, and a wizard-driven web UI as the only user-facing
surface for normal operation.

## 2. Goals

1. A first-time user with a Pi + camera can go from `git`-less hardware to a
   working, calibrated speed camera in under 15 minutes with zero shell
   commands beyond the initial three-line install.
2. Re-calibration takes under 60 seconds and never involves text editing,
   pixel counting, or restarts.
3. The codebase is structured so the detector, camera, storage, and server
   are independently testable units with explicit boundaries.
4. The full stack is reproducible on any developer's laptop via Docker, with
   a file-replay camera source — no Pi required to develop the UI.
5. Settings changes propagate live to the running pipeline without a
   container restart.
6. The project is suitable for the Pi-hobbyist / homelab audience
   (Octoprint-tier polish: real docs, real install, but not enterprise QA).

## 3. Non-goals

- Multi-tenant / per-user accounts.
- A hosted / cloud version.
- Windows-native install (Docker on Windows is supported; native is not).
- Drop-in upgrade path from `pageauc/speed-camera` (config schema, DB schema,
  install model all differ; we are not a fork).
- Editing camera firmware or supporting non-OpenCV-compatible capture devices.

## 4. Architecture

### 4.1 Module Layout

```
curbcam/
├── docker-compose.yml             (the only install path)
├── Dockerfile                     (multi-arch: arm64 + amd64)
├── pyproject.toml                 (uv-managed)
├── src/curbcam/
│   ├── detector/                  ← pure CV library, no I/O, no globals
│   │   ├── motion.py              (contour detection)
│   │   ├── tracker.py             (frame-to-frame correlation)
│   │   ├── calibration.py         (px→mm, speed calc)
│   │   └── types.py               (Detection, TrackedObject dataclasses)
│   ├── camera/                    ← frame source abstraction
│   │   ├── base.py                (Camera protocol)
│   │   ├── picamera2_source.py    (Pi cam via libcamera)
│   │   ├── usb_source.py          (OpenCV /dev/video0)
│   │   ├── rtsp_source.py         (OpenCV RTSP, with reconnect)
│   │   ├── file_replay.py         (dev/test source — replays JPEG dir)
│   │   └── factory.py             (string → Camera)
│   ├── config/                    ← Pydantic settings, persisted to YAML
│   │   ├── schema.py
│   │   ├── store.py
│   │   └── defaults.py            (single source of truth for labels + help)
│   ├── storage/                   ← SQLite + media files
│   │   ├── db.py                  (SQLAlchemy + Alembic migrations)
│   │   ├── models.py              (Event, Calibration)
│   │   └── media.py               (image + thumbnail paths, rotation)
│   ├── pipeline/                  ← the orchestrator
│   │   ├── runner.py              (camera→detector→storage loop)
│   │   └── events.py              (in-process pub-sub for SSE)
│   ├── server/                    ← FastAPI app
│   │   ├── app.py                 (factory + DI wiring)
│   │   ├── routes/{stream,events,settings,calibration,auth}.py
│   │   ├── templates/             (Jinja for HTMX)
│   │   └── static/                (CSS + small JS for canvas)
│   └── cli.py                     (uv run curbcam {serve,db,calibrate})
└── tests/{unit,integration}/
```

### 4.2 Boundary rules

- `detector/` knows nothing about cameras, storage, or web. Pure functions
  over numpy arrays. Fully unit-testable with synthetic frames; no hardware
  in CI.
- `camera/` knows nothing about detection or web. It yields frames.
- `pipeline/runner.py` is the **only** module that wires
  camera → detector → storage. Everything else is observable through it.
- `server/` depends on `pipeline/events.py` (live), `storage/` (history),
  and `config/` (settings). It **never** depends on the detector directly.
- `config/` is the contract between the UI and the runner: the UI writes
  config, the runner re-reads it on its next frame iteration.

### 4.3 Process model

A single Python process inside one container. The pipeline runner uses a
**background thread** for camera reads + detection (CPU-bound numpy/OpenCV
work would otherwise stall the asyncio event loop and hurt MJPEG streaming).
FastAPI runs on the main asyncio loop. The two communicate via a thread-safe
`queue.Queue` bridged into asyncio with `loop.call_soon_threadsafe`.

**Single-process tradeoff:** a detector crash takes the web server down with
it; Docker restarts the container automatically (brief gap). Acceptable for
hobbyist scope. Revisit only if it bites in practice.

## 5. Detector

### 5.1 Public API

```python
# detector/types.py
@dataclass(frozen=True)
class Detection:
    bbox: tuple[int, int, int, int]    # x, y, w, h in source-image pixels
    centroid: tuple[int, int]
    area_px: int
    frame_ts: float                     # monotonic seconds

@dataclass(frozen=True)
class TrackedObject:
    id: str                             # short uuid, stable across frames
    detections: list[Detection]
    direction: Literal["L2R", "R2L"] | None
    speed_kph: float | None             # None until calibrated + enough frames

# detector/motion.py
def find_motion(prev_gray, curr_gray, *, min_area_px, crop) -> list[Detection]: ...

# detector/tracker.py
class Tracker:
    def __init__(self, max_dist_px: int, min_track_frames: int): ...
    def update(self, detections) -> list[TrackedObject]:
        """Returns tracks finalized this frame (object left, lost, or completed)."""

# detector/calibration.py
@dataclass(frozen=True)
class Calibration:
    mm_per_px_l2r: float
    mm_per_px_r2l: float

def speed_from_track(track, cal) -> float | None: ...
```

### 5.2 Key change from upstream

Direction-specific calibration is one `Calibration` dataclass, not four loose
globals (`CAL_OBJ_PX_L2R`, `CAL_OBJ_MM_L2R`, etc.). The wizard produces one
per save; the runner reads it per event. The detector never reaches into
config or globals.

## 6. Camera Abstraction

```python
# camera/base.py
class Camera(Protocol):
    def open(self) -> None: ...
    def read(self) -> tuple[NDArray, float] | None:  # (frame_bgr, monotonic_ts)
        """Returns None on transient failure (caller retries with backoff)."""
    def close(self) -> None: ...
    @property
    def resolution(self) -> tuple[int, int]: ...
    @property
    def fps_target(self) -> float: ...
```

Four day-one implementations: `Picamera2Source`, `UsbSource`, `RtspSource`,
`FileReplaySource`. The factory takes a config-driven string:
`"picamera2:0"`, `"usb:/dev/video0"`, `"rtsp://..."`, `"file:./fixtures/run1"`.
Adding RTMP / GoPro / etc. later is one file + one factory line.

**picamera2 specifically:** used directly, no `rpicam` shim, no symlinks.
picamera2 is the supported libcamera path on Raspberry Pi OS Bookworm and
later. The Docker container mounts `/run/udev`, `/dev/dma_heap`, and
`/dev/video*` so it works without user-side symlinks. Documented in the
install README.

## 7. Storage

### 7.1 SQLite schema (Alembic-managed from day one)

```sql
-- one row per finalized track
CREATE TABLE events (
    id             INTEGER PRIMARY KEY,
    ts_utc         TIMESTAMP NOT NULL,
    speed_kph      REAL NOT NULL,
    direction      TEXT NOT NULL,                -- 'L2R' | 'R2L'
    frame_count    INTEGER NOT NULL,
    track_len_px   INTEGER NOT NULL,
    image_path     TEXT NOT NULL,                -- relative to media root
    thumb_path     TEXT NOT NULL,
    calibration_id INTEGER REFERENCES calibrations(id)
);
CREATE INDEX events_ts ON events(ts_utc DESC);

-- every wizard run snapshotted, never overwritten
CREATE TABLE calibrations (
    id                    INTEGER PRIMARY KEY,
    created_utc           TIMESTAMP NOT NULL,
    mm_per_px_l2r         REAL NOT NULL,
    mm_per_px_r2l         REAL NOT NULL,
    reference_distance_mm REAL NOT NULL,
    reference_points_json TEXT NOT NULL,         -- where the user clicked
    active                BOOLEAN NOT NULL,
    notes                 TEXT
);
CREATE UNIQUE INDEX one_active_calibration
    ON calibrations(active) WHERE active = 1;
```

**Connection mode:** WAL journaling is enabled at first-open
(`PRAGMA journal_mode=WAL`). The detector thread writes events while the
server thread reads history; WAL means readers never block the writer and
vice versa. This is the default in modern Python but stated explicitly
because the single-process / two-thread model depends on it.

**Why store calibration history:** when speeds drift unexpectedly (camera
moved, lens fogged, season changed), being able to say "events Tuesday used
calibration #3, Wednesday onward used #4" is a real debugging lifeline.

### 7.2 Media layout

```
media/
├── events/YYYY/MM/DD/event_<id>.jpg     (full frame, source resolution)
├── thumbs/YYYY/MM/DD/event_<id>.jpg     (320 px wide, source aspect ratio preserved)
└── alignment/                            (transient preview frames)
```

Thumbnails preserve the source aspect ratio rather than forcing a fixed
height because cameras ship in 4:3, 16:9, and other ratios — squishing a
1280×960 Pi Cam frame to 320×180 looks bad and loses detail. The
dashboard grid layout (MVP-2) sets a fixed `width: 320px; height: auto;`
on each thumbnail `<img>` so uneven heights flow naturally.

Date-bucketed so a year of events doesn't dump 100k files in one folder.
Rotation is a single background task driven by `max_events_per_day` and
`max_total_disk_mb` config knobs — centralized, not scattered across
scripts.

**Annotation on saved JPEGs:** the full-frame `events/.../event_<id>.jpg`
is saved with a minimal overlay (timestamp + measured speed + direction
arrow) burned into a bottom strip — enough to be useful when viewed
standalone, sparse enough not to obscure plate/vehicle detail. Thumbnails
get the same overlay scaled. The live MJPEG stream and the alignment
wizard's "show detection overlay" mode draw additional context
(bounding boxes, crop region) that is **not** persisted to disk.

### 7.3 CSV

No CSV file on disk. The same data is in SQLite, with indexes and
transactions. `GET /api/events.csv?filters` generates CSV on demand for
spreadsheet users.

## 8. Web Server & UI

### 8.1 Route surface

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Dashboard page |
| `GET` | `/events` | History page |
| `GET` | `/settings` | Settings page |
| `GET` | `/setup` | First-run wizard host |
| `GET` | `/api/stream.mjpeg` | Live preview (`multipart/x-mixed-replace`) |
| `GET` | `/api/events/stream` | SSE: push new events |
| `GET` | `/api/events?filters` | History JSON for HTMX partial |
| `GET` | `/api/events.csv?filters` | On-demand CSV export |
| `POST/PUT` | `/api/settings` | Save Pydantic-validated config |
| `POST` | `/api/calibration/capture` | Freeze a frame for measurement |
| `POST` | `/api/calibration/measure` | Save (points, distance, direction) |
| `POST` | `/api/crop` | Save crop region from alignment wizard |
| `POST/DELETE` | `/api/auth/login` `/api/auth/logout` | Session cookie |
| `GET` | `/api/debug/stats` | Detector FPS, queue depths, uptime (JSON) |

`/api/stream.mjpeg` accepts **either** a valid session cookie **or** a valid
stream token query parameter (see §10). `/api/auth/login` is the only
fully-public endpoint. Everything else requires a session cookie.

### 8.2 Pages

- **Dashboard (`/`):** live MJPEG (throttled to 5 fps), "currently tracking"
  pill, last 10 events as thumbnail cards with speed + direction + relative
  time. SSE updates the card list in place.
- **Events (`/events`):** filterable history (date range, speed range,
  direction), server-side pagination, click-to-modal full image, CSV export.
  All timestamps are stored UTC and rendered in the browser's local timezone
  (client-side `toLocaleString`) — Pi `TZ` env var is for log files only.
- **Settings (`/settings`):** Primary + Advanced tabs, Pydantic-validated
  server-side, HTMX inline errors.
- **Calibration & Alignment (`/setup/calibrate`, `/setup/align`):** detailed
  in §8.3 and §8.4.
- **First-run (`/setup`):** when no admin password OR no active calibration
  exists, **all** routes 302 to `/setup`. Five linear steps: set password →
  pick camera source → confirm live preview → alignment → calibration.

### 8.3 Calibration wizard (the killer feature)

1. **Capture a reference frame.** Live preview with overlay text guiding the
   user to place a known-length object (parked car's wheelbase, fence panel,
   chalk line). Big "Capture" button. Click → server returns frozen JPEG +
   dimensions.
2. **Click two points.** Frozen image renders into an `<img>` + transparent
   `<canvas>` overlay. Click point A → red dot. Click point B → second dot +
   connecting line with pixel-distance label. "Undo last point" and "Start
   over" available. Below: text input for real-world distance + units
   dropdown (m / ft / in / mm) + direction selector (L2R / R2L). Submit.
3. **Confirm + sanity check.** Server computes
   `mm_per_px = typed_distance_mm / pixel_distance`, stores as a new active
   calibration row, shows the result, prompts the user to drive a
   known-speed vehicle past for verification. SSE pushes the next 3 events
   with a "verify mode" badge.
4. **Save or recalibrate.** *"Looks right"* finalizes; *"Off, try again"*
   loops back to step 1.

**Crucial implementation detail:** the canvas is almost certainly displayed
at a different resolution than the source frame (e.g. 1920×1080 source,
960×540 display). Click coordinates must be scaled back to source
coordinates before sending to the server. Easy to get wrong; the spec calls
it out to prevent shipping a calibration that's off by 2x.

### 8.4 Alignment wizard

Live preview + transparent canvas overlay. User drags a rectangle. Submit →
saved as crop region. Optional toggle *"Show motion-detection overlay"*
streams the same MJPEG but with the runner's contour boxes drawn in green,
so the user can see what would actually be detected through the current
crop. This single feature replaces the upstream "save image to file, scp to
laptop, look, change config, restart, repeat" loop.

### 8.5 Live MJPEG + SSE

- **MJPEG:** `StreamingResponse(media_type="multipart/x-mixed-replace; boundary=frame")`.
  The runner publishes the latest annotated frame to a `latest_frame:
  Optional[bytes]` slot; the stream endpoint reads-and-yields at 5 fps
  regardless of camera FPS. One frame slot, no per-client queue, no
  backpressure issues.
- **SSE:** `text/event-stream`, simple `async def` generator awaiting an
  `asyncio.Queue` per connected client. Runner finalizes an event →
  `events.publish(event)` → fan-out to all connected client queues.
  Disconnected clients drop their queue; no state leaks.
- **Pluggability:** `events.publish(event)` is the single fanout point.
  v0.2 alert subscribers (webhook, MQTT, ntfy) plug in here with the same
  contract the SSE generator uses today. Spec'd as a design property so the
  v0.2 work is additive, not invasive.

### 8.6 Settings → runner propagation

The runner reads a `RuntimeConfig` snapshot at the top of every frame
iteration via an atomic reference swap. Settings save = Pydantic validate →
write YAML → swap snapshot. Hot-reload for everything except camera-source
change, which triggers a clean `close` + `open` on the camera thread.
**No container restart is needed for any settings change.**

## 9. Configuration Model

Single Pydantic-settings schema, YAML on disk at `/data/curbcam.yaml`,
defaults in `config/defaults.py`, env-var overrides allowed for Docker
convenience.

```python
class CameraSettings(BaseModel):
    source: str = "picamera2:0"
    resolution: tuple[int, int] = (1280, 720)
    fps_target: float = 15.0

class DetectorSettings(BaseModel):
    min_area_px: int = 800
    min_track_frames: int = 5
    max_dist_px: int = 100
    crop: BBox | None = None             # set by alignment wizard

class RetentionSettings(BaseModel):
    max_events_per_day: int = 500
    max_total_disk_mb: int = 5000

class ServerSettings(BaseModel):
    units: Literal["kph", "mph"] = "kph"
    min_event_speed_kph: float = 5.0           # enforced in pipeline/runner.py
                                               # before storage write; tracks
                                               # below this are dropped silently
    log_level: Literal["DEBUG", "INFO", "WARNING"] = "INFO"

class Settings(BaseModel):
    camera: CameraSettings = CameraSettings()
    detector: DetectorSettings = DetectorSettings()
    retention: RetentionSettings = RetentionSettings()
    server: ServerSettings = ServerSettings()
```

~30 fields total. Each gets a label + help text in `defaults.py` consumed by
the settings UI — **single source of truth.**

**Env-var overrides for sensitive fields.** Pydantic-settings supports
nested env-var overrides natively (`CURBCAM_CAMERA__SOURCE` overrides
`camera.source`). The install README and `docker-compose.yml` example
demonstrate this for `camera.source` so users can keep RTSP credentials
in `.env` (gitignored) rather than `curbcam.yaml`. The UI shows a
"set via environment" indicator on any field overridden by env, and
makes it read-only in the form.

Calibration is **not** in YAML — it lives in SQLite (active row + history)
because it is user-generated data, not configuration.

## 10. Auth

Single admin password, set on first-run. Stored as Argon2 hash in
`/data/auth.json`. Session via `itsdangerous`-signed cookie, 30-day sliding
expiry. **No JWT, no OAuth, no multi-user, no roles.** Users who need more
can put Caddy / Authelia / Tailscale in front.

For embedding the live MJPEG in Home Assistant or similar, settings can mint
per-purpose read-only stream tokens (`?token=...`) usable as a query-param
auth on `/api/stream.mjpeg`. Tokens are revocable from settings. The
endpoint sets `Referrer-Policy: strict-origin-when-cross-origin` so the
token cannot leak to third-party sites via `Referer` headers when the
stream is embedded.

## 11. Install & Deployment

### 11.1 Docker Compose (the only install path)

```yaml
services:
  curbcam:
    image: ghcr.io/PatientVibes/curbcam:latest
    restart: unless-stopped
    ports: ["8080:8080"]
    volumes:
      - ./data:/data            # YAML, sqlite, auth.json
      - ./media:/media          # event images + thumbs
      - /run/udev:/run/udev:ro
    devices:
      - /dev/video0:/dev/video0       # USB cam (if used)
      - /dev/dma_heap:/dev/dma_heap   # picamera2/libcamera
    environment:
      - TZ=America/Los_Angeles
    env_file:
      - .env                  # CURBCAM_CAMERA__SOURCE=rtsp://user:pw@... etc.
```

A gitignored `.env` keeps RTSP credentials and any other secrets out of
`curbcam.yaml`. The image otherwise needs no environment setup.

### 11.2 Image build

Multi-arch (`linux/arm64` for Pi 4/5, `linux/amd64` for x86 dev), built by
GitHub Actions on tag push. `latest` tracks `main`; semver tags for
releases. Published to GHCR.

### 11.3 Discovery

The container runs avahi and advertises itself as `curbcam.local`. After
`docker compose up`, the user opens `http://curbcam.local:8080`. Fallback:
container logs print `Open http://<detected-ip>:8080` if mDNS is unavailable.

### 11.4 User install path

```bash
mkdir curbcam && cd curbcam
curl -O https://raw.githubusercontent.com/PatientVibes/curbcam/main/docker-compose.yml
docker compose up -d
# browse to http://curbcam.local:8080
```

Three commands.

## 12. Testing

- **Unit — detector:** synthetic frames via numpy/PIL (black canvas with a
  moving white rectangle). Assert `find_motion` returns the right bbox;
  `Tracker` produces one track with the right direction; `speed_from_track`
  returns expected kph given known px/frame + timestamps + calibration.
  No hardware required; runs in CI.
- **Unit — config:** YAML round-trip stability; v1 → v2 migration test
  (sets up the upgrade story before it becomes a problem).
- **Integration — server:** `httpx.AsyncClient` against the FastAPI app with
  `FileReplaySource` as the camera. End-to-end calibration wizard test:
  POST capture → POST measure → GET active calibration → finalize a track →
  assert event arrives via SSE with the right speed.
- **One Playwright smoke test** for the calibration wizard end-to-end:
  open `/setup/calibrate` against a FileReplaySource container, capture a
  reference frame, click two points at known canvas coordinates, submit a
  known reference distance, assert the resulting `Calibration` row's
  `mm_per_px_l2r` matches the hand-computed value within tolerance. This
  single test catches the canvas-coordinate-transform bug class (§8.3)
  that unit tests fundamentally cannot. Everything else stays manual-smoke
  for MVP scope.
- **CI:** GitHub Actions on `python: 3.12` / `arch: amd64`. Multi-arch
  Docker build (`arm64` + `amd64`) on tag. Playwright runs in a
  separate job against a Docker-Compose'd FileReplaySource container.

## 13. MVP Cut Line

### 13.1 In MVP (v0.1)

- `picamera2`, USB, RTSP camera sources + `FileReplaySource`
- Motion detection, tracking, calibrated speed (L2R + R2L)
- Calibration history in SQLite
- Live MJPEG preview + SSE event feed
- Dashboard, Events history, Settings (Primary + Advanced)
- First-run wizard, Calibration wizard, Alignment wizard
- Single admin password + session; per-purpose stream tokens
- Multi-arch Docker image, mDNS, three-command install
- Retention by per-day cap + total disk cap
- CSV export on demand
- Unit + integration tests in CI

### 13.2 Deferred to v0.2+

- Alerts (webhook, MQTT, ntfy on threshold) — clean to add, pipeline events
  are already pub-sub
- Graphs page / Reports tab
- Cloud sync (rclone equivalent)
- ALPR / license-plate OCR
- Vehicle classification (YOLO etc.)
- Multi-camera per instance
- Pre-flashed SD image via pi-gen
- Time-lapse / video clips
- Home Assistant custom integration (community can build on the stable API)
- Day/night detection (gating low-light image saves, à la upstream's
  `is_daytime` / `IM_SAVE_4AI_DAY_THRESH`) — defer until we know users
  actually run into the disk-pressure-from-junk-frames problem; retention
  caps already bound the worst case.

### 13.3 Non-goals (probably never)

- Multi-tenant / per-user accounts
- Cloud-hosted version
- Windows-native install
- Editing camera firmware / supporting non-OpenCV capture devices

## 14. Risks

- **picamera2 + Docker on Pi 5 is the riskiest assembly.** Mitigated by
  pinning the install README to Raspberry Pi OS Bookworm or newer.
- **Detector parity with upstream is not guaranteed.** A synthetic-frame
  regression suite catches the obvious cases but cannot replicate every
  edge case upstream has tuned for over years. Documented as
  "may differ from upstream; report regressions."
- **Single-process crash blast radius:** detector crash → web server down →
  Docker restarts. Brief gap. Acceptable; revisit only if it bites.
- **Plaintext credentials in YAML.** `camera.source` for RTSP cameras
  embeds `user:password@host`. Mitigated by the env-var override path
  (§9) and the `.env` pattern in §11.1, both documented in the install
  README. Risk remains if a user pastes credentials directly into
  `curbcam.yaml`; UI shows a "this field contains credentials —
  consider env var" hint on detection of `user:` in the URL.

## 15. Responsible Use & Privacy

Speed cameras inherently capture imagery of people, vehicles, and license
plates in public or semi-public spaces. The legal status of doing so varies
by jurisdiction (GDPR in the EU, state-by-state in the US, etc.) and is not
something this project can resolve for the user.

The project's stance:

- **The README's "Before you install" section must warn the operator to
  check their local laws** before pointing the camera at a public road or
  shared space. This is non-optional documentation.
- **The default install is private-network-only** — no UPnP, no port
  forwarding, no cloud sync, no public listing. The user has to actively
  expose the service to make it externally accessible.
- **No license-plate OCR ships in the MVP** (it's deferred — §13.2). If
  added later, it ships disabled by default with a separate "I understand
  the legal implications" consent step.
- **No facial recognition. Ever.** Listed as a non-goal.
- **All captured imagery stays on the user's device** unless they
  explicitly opt into cloud sync (deferred, §13.2). Nothing phones home.
- The `media/events/` directory is local-only by design; the user owns
  the data and can delete it at any time. A "delete all events older
  than N days" button lives in Settings.

This section is also surfaced in the first-run wizard as a single
acknowledgment screen before the user lands on the dashboard.

## 16. Open Questions

None at design time. Implementation plan will surface specifics
(exact OpenCV background-subtractor choice, MJPEG fps cap defaults, etc.).
