# curbcam MVP-2 — Web Layer Design

**Status:** Design (brainstormed 2026-05-28). Supersedes the web-layer mechanism
details in the overall design spec (`2026-05-28-curbcam-design.md` §8–§10) where
they differ — see §0.

**Goal:** Ship the user-facing half of curbcam: a single-process web app that
runs the detector pipeline in a background thread and exposes a wizard-driven,
LAN-only UI. After MVP-2, a non-technical user can go from a fresh install to a
calibrated, running speed camera in minutes with zero shell access.

**Builds on:** MVP-1 (`v0.1.0-mvp-1`) — the detector library, `camera/`,
`config/`, `storage/`, `pipeline/runner.py`, and the `EventBus`. MVP-2 adds a new
`web/` package and a `curbcam serve` CLI command. It does **not** rewrite the
detector or storage layers.

**Reference:** Overall design spec at `docs/specs/2026-05-28-curbcam-design.md`
(sections cited as §N). This document is the MVP-2-specific, implementation-ready
design.

---

## 0. Decisions that diverge from the overall design spec

Two deliberate divergences, agreed during brainstorming:

1. **Settings propagation = graceful pipeline-thread restart, not in-thread
   hot-reload.** The overall spec §8.6 prescribes a `RuntimeConfig` snapshot read
   at the top of every frame loop via an atomic reference swap. MVP-2 instead
   tears down and rebuilds the pipeline thread on save (see §5). Both satisfy the
   spec's user-facing promise ("no *container* restart needed"); the restart is
   simpler, uniformly correct for every field including camera
   source/resolution, and costs only a ~1–2 s detection gap on the rare event of
   a settings edit. §8.6's mechanism is therefore superseded by this document.

2. **Speed/calibration model stays two-scale (`mm_per_px_l2r` /
   `mm_per_px_r2l`); the planar-homography model is deferred** to a separate
   "calibration v2" spec (see §9). Rationale and the supporting geometry analysis
   are in §9.

---

## 1. Scope

In scope for MVP-2 (the full §13.1 web surface):

- `curbcam serve` — single-process app: uvicorn + a detector pipeline thread.
- Auth: single admin password (Argon2), itsdangerous-signed session cookie,
  revocable per-purpose stream tokens.
- Pages: Dashboard, Events history, Settings (Primary + Advanced).
- Wizards: First-run, Alignment, Calibration.
- Live MJPEG preview (5 fps) + SSE event/stats feed.
- CSV export on demand.
- Settings → live pipeline propagation via graceful restart.
- Unit + integration tests (FastAPI `TestClient`, `FileReplaySource`, no
  hardware) + one Playwright smoke test for the calibration wizard.

Out of scope (later milestones / deferred):

- Docker image, multi-arch build, mDNS, three-command install → **MVP-3**
  (MVP-2 only provides the clean `curbcam serve` entrypoint as the seam).
- Planar-homography calibration → **calibration v2** (§9).
- Alerts (webhook/MQTT/ntfy), graphs page, cloud sync, ALPR, vehicle
  classification → v0.2+ (§13.2 of the overall spec).

---

## 2. Architecture

Single OS process (`curbcam serve`), matching the overall spec's single-process
crash model (§14: detector crash → web down → supervisor/Docker restarts; brief
gap accepted).

```
            ┌──────────────────────── curbcam serve (one process) ───────────────────────┐
            │                                                                             │
  HTTP ───► │  uvicorn ─► FastAPI app (create_app)                                        │
            │     │         routes/* ─ pages, auth, events, stream, settings,             │
            │     │                    calibration, crop, debug                           │
            │     │                                                                        │
            │     ▼                                                                        │
            │  Supervisor (app.state) ── owns ──┬─ ConfigStore  ─ curbcam.yaml             │
            │     │                              ├─ Database     ─ curbcam.sqlite (WAL)    │
            │     │                              ├─ EventBus     ─ SSE fanout              │
            │     │                              ├─ MediaWriter  ─ media/ (JPEGs/thumbs)   │
            │     │                              ├─ Calibration/EventRepo                  │
            │     │                              └─ AuthStore    ─ auth.json               │
            │     │                                                                        │
            │     └─ runs ─► PipelineRunner (background thread)                            │
            │                  camera.read ─► find_motion ─► Tracker ─► persist + bus      │
            │                  └─ latest_frame: bytes|None  (annotated JPEG, 1 slot)       │
            └─────────────────────────────────────────────────────────────────────────────┘
```

**Composition root.** `create_app(supervisor) -> FastAPI` is a pure function of an
injected `Supervisor`. It registers routers, mounts `/static` and a read-only
mount of the media dir (to serve event JPEGs/thumbs), installs middleware
(session, first-run gate), and wires startup/shutdown hooks. Because the app is a
function of the supervisor, the entire app is testable with a
`FileReplaySource`-backed supervisor and no hardware.

**Why a single `Supervisor`:** one clear owner for all long-lived state and the
pipeline lifecycle. Routes depend only on `Supervisor` (via a FastAPI
dependency), never on globals.

Approaches considered and rejected: two-process web+detector over IPC (adds
serialization + frame-shipping, contradicts the deliberate single-process
choice); pure-asyncio detector task (OpenCV reads are blocking/CPU-bound, would
need `run_in_executor` = threads with extra ceremony).

---

## 3. Module layout

New package `src/curbcam/web/` (sibling to `pipeline/`, `storage/`):

```
web/
├── __init__.py
├── app.py            # create_app(supervisor) -> FastAPI
├── supervisor.py     # Supervisor: owns runner thread, EventBus, DB, ConfigStore; .restart()
├── deps.py           # get_supervisor, require_session, require_stream_auth
├── auth.py           # Argon2 hashing, itsdangerous cookie + stream-token signing, AuthStore
├── streams.py        # MJPEG generator (latest_frame @5fps) + SSE generator (bus queue)
├── units.py          # kph<->mph conversion + display formatting (shared by CSV + UI)
├── routes/
│   ├── __init__.py
│   ├── pages.py      # GET /, /events, /settings, /setup, /setup/align, /setup/calibrate
│   ├── auth.py       # POST /api/auth/login, DELETE /api/auth/logout
│   ├── events.py     # GET /api/events, /api/events.csv, /api/events/stream (SSE)
│   ├── stream.py     # GET /api/stream.mjpeg
│   ├── settings.py   # GET form partials, POST/PUT /api/settings -> validate, save, restart
│   ├── calibration.py# POST /api/calibration/capture, /api/calibration/measure
│   ├── crop.py       # POST /api/crop (alignment wizard)
│   └── debug.py      # GET /api/debug/stats
├── templates/        # Jinja2: base.html + dashboard/events/settings/setup partials
└── static/           # app.css, app.js, vendored htmx (no CDN — LAN-only device)
```

**CLI.** Add `curbcam serve --host --port --config --data-dir` alongside the
existing `detect` / `calibrate` / `db init`. `serve` builds a `Supervisor` from
`Settings` + the data dir, calls `create_app`, and hands the app to
`uvicorn.run`. The `detect` and `calibrate` CLIs remain (the overall spec keeps
`{serve, db, calibrate}`).

**New dependencies:** `fastapi`, `uvicorn[standard]`, `jinja2`,
`python-multipart` (form posts), `itsdangerous` (cookie + token signing),
`argon2-cffi` (password + token hashing). htmx is **vendored** into `static/`
(no CDN dependency on a LAN-only device).

---

## 4. Supervisor, lifecycle & the live-frame tap

```python
class Supervisor:
    def __init__(self, *, config_store, db, bus, media_root, auth_store): ...
    # owns: ConfigStore, Database, EventBus, CalibrationRepo, EventRepo,
    #       MediaWriter, AuthStore, current PipelineRunner + its thread

    def start(self) -> None        # bind_loop; build camera+runner from Settings; run_in_background_thread
    def stop(self) -> None         # runner.stop(); join
    def restart(self) -> None      # stop -> reload Settings -> rebuild -> start; publish settings_changed
    @property
    def latest_frame(self) -> bytes | None   # most recent annotated JPEG, or None
    def add_viewer(self) -> None / remove_viewer(self) -> None   # MJPEG viewer refcount
    def set_overlay(self, on: bool) -> None   # alignment-wizard contour overlay
    def capture_still(self) -> tuple[bytes, int, int]   # frozen JPEG + (w, h) for calibration
    def stats(self) -> dict        # fps, uptime, frames seen, tracking? -> /api/debug/stats
```

**Concurrency invariant.** `start()` / `stop()` / `restart()` are serialized by a
single `threading.Lock` held on the `Supervisor`. This prevents overlapping
restarts (e.g. two near-simultaneous `/api/settings` saves) from racing to
`.join()` and replace the runner thread, which would otherwise leave the
supervisor pointing at a half-built or already-dead thread. Concurrent restart
requests block on the lock and apply the latest persisted `Settings` in order; a
restart already in progress is not duplicated.

**Live-frame tap (overall spec §8.5).** The `PipelineRunner` gains an optional
frame sink set by the supervisor. Each iteration, after motion processing, the
runner: (1) optionally draws contour boxes (green) when overlay mode is on;
(2) JPEG-encodes the frame (`cv2.imencode`); (3) writes the bytes into a single
`latest_frame` slot under a lock (overwrite, no queue, no per-client
backpressure). To avoid wasting CPU when nobody is watching, the runner encodes
only when `viewers > 0` **or** overlay mode is active; otherwise `latest_frame`
goes stale and is treated as `None`.

**MJPEG read path.** `/api/stream.mjpeg` reads the slot and yields at 5 fps
regardless of camera FPS — exactly the spec's "one frame slot" design.

**`capture_still` reuses the buffered frame — no mid-loop re-entrancy.** The
`PipelineRunner` already keeps the most recent decoded full BGR frame in memory
(`runner.py:82`, `last_full_frame = frame_bgr`). `capture_still()` does **not**
ask the loop to grab a fresh frame on demand and does **not** open a second
camera handle (most camera backends are single-consumer). Instead the runner
writes a copy of each decoded full frame into a thread-safe `last_full_frame`
snapshot slot (separate from the annotated MJPEG slot, un-annotated, full
resolution) under a lock, and `capture_still()` simply reads-and-encodes that
slot. This makes capture a lock-protected read of shared state rather than a
re-entrant interaction with the running loop — no deadlock surface, no
prev/curr-frame desync. Cost: the calibration still may be up to ~1 frame
(~66 ms) old, which is irrelevant for a static reference measurement.

**Lifecycle / threading.**
- A FastAPI startup hook calls `bus.bind_loop(asyncio.get_running_loop())` so the
  detector thread's `publish_threadsafe` can bridge into the loop for SSE, then
  calls `supervisor.start()`.
- Shutdown calls `supervisor.stop()`.
- `restart()` is synchronous and quick; the settings/crop/camera routes call it
  **inside `run_in_threadpool`** so the event loop (and thus other clients'
  SSE/MJPEG) is not stalled during the ~1–2 s rebuild.
- Crash/reconnect behavior is unchanged from MVP-1: `_loop_with_reconnect`
  already retries persistent sources and cleanly exits finite ones, resetting the
  `Tracker` on crash so stale `frame_ts` values cannot poison the first
  post-reconnect speed reading.

**`PipelineRunner` changes required (additive, must keep MVP-1 tests green):**
- accept an optional `on_frame`/frame-sink + a `viewers`/overlay signal,
- expose enough for `Supervisor.capture_still()` (grab the latest decoded BGR),
- expose lightweight stats (fps, tracking flag, uptime) for `stats` envelopes.

---

## 5. Settings → live pipeline propagation

`POST/PUT /api/settings` flow:

1. Parse form → build candidate `Settings` → **Pydantic validation**. On failure,
   return 422 and htmx-swap inline field errors next to the offending inputs.
2. On success: `ConfigStore.save(settings)`.
3. `await run_in_threadpool(supervisor.restart)` — stop the runner thread, reload
   `Settings`, rebuild camera+runner, start. Publishes a `settings_changed`
   envelope so the UI can show a brief "restarting…" toast.

The same restart path is used by `POST /api/crop` (alignment) and by the
first-run camera-source step. **Calibration changes do not restart** — they are
read per-event via `CalibrationRepo.get_active()`, so a new active calibration
applies to the next vehicle immediately.

**Env-var overrides (§9 of overall spec).** Fields overridden by an env var
(e.g. `CURBCAM_CAMERA__SOURCE`) render **read-only** in the form with a "set via
environment" badge. Saving the form does not attempt to persist env-shadowed
values into YAML (the known MVP-1 caveat is sidestepped because the form submits
only editable fields).

---

## 6. Auth & access control (overall spec §10)

Single admin password. No users, roles, JWT, or OAuth.

**Storage — `data/auth.json`:**
```json
{
  "password_hash": "<argon2>",
  "secret_key": "<random, generated once>",
  "stream_tokens": [
    { "id": "...", "label": "Home Assistant", "token_hash": "<argon2>", "created_utc": "..." }
  ]
}
```
`secret_key` is generated once when the password is first set and used by
`itsdangerous` to sign session cookies and stream tokens. `AuthStore` wraps
read/write. Passwords and stream tokens are stored **only** as Argon2 hashes; a
raw stream token is shown to the user exactly once at mint time (like an API
key).

**Sessions.** `POST /api/auth/login` verifies the password and sets an
itsdangerous-signed cookie (`HttpOnly`, `SameSite=Lax`; `Secure` omitted because
LAN/HTTP is the norm) with a 30-day sliding expiry refreshed on each
authenticated request. `DELETE /api/auth/logout` clears it.

**Gate (middleware + dependency).**
- **First-run redirect middleware:** if `auth.json` has no password **or** there
  is no active calibration row, every route except `/setup*`,
  `/api/auth/login`, `/api/calibration/*`, `/api/crop`, and `/static/*` returns a
  302 to `/setup`.
- `require_session` dependency protects all other routes. `/api/auth/login` is
  the only fully public endpoint.
- `/api/stream.mjpeg` uses `require_stream_auth`: accepts **either** a valid
  session cookie **or** a valid `?token=` stream token, and sets
  `Referrer-Policy: strict-origin-when-cross-origin` so an embedded stream cannot
  leak the token via `Referer`.

**Stream tokens.** Minted/revoked from Settings → "Integrations". Signed, labeled,
revocable (revoke = remove its hash from `auth.json`). For embedding the MJPEG
feed in Home Assistant etc.

**Threat model (stated, not solved).** LAN-only by default. Brute-force
resistance = a fixed ~250 ms compare delay on login + Argon2's inherent cost; no
lockout/rate-limit table in MVP-2. WAN exposure is the user's responsibility
(Caddy / Authelia / Tailscale), per the overall spec.

---

## 7. HTTP surface

Per overall spec §8.1. All endpoints require a session cookie except where noted.

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Dashboard page |
| GET | `/events` | History page |
| GET | `/settings` | Settings page (Primary + Advanced tabs) |
| GET | `/setup` | First-run wizard host |
| GET | `/setup/align` | Alignment wizard |
| GET | `/setup/calibrate` | Calibration wizard |
| GET | `/api/stream.mjpeg` | Live preview (`multipart/x-mixed-replace`); cookie **or** `?token=` |
| GET | `/api/events/stream` | SSE: push new events + stats |
| GET | `/api/events?filters` | Filtered history JSON/partial for htmx |
| GET | `/api/events.csv?filters` | On-demand CSV export (streamed) |
| POST/PUT | `/api/settings` | Validate + save config, then graceful restart |
| POST | `/api/calibration/capture` | Freeze a frame for measurement |
| POST | `/api/calibration/measure` | Save (points, distance, units, direction) |
| POST | `/api/crop` | Save crop region from alignment wizard |
| POST | `/api/auth/login` | Set session cookie (only public endpoint) |
| DELETE | `/api/auth/logout` | Clear session cookie |
| GET | `/api/debug/stats` | Detector fps, uptime, tracking flag (JSON) |

---

## 8. Pages, streams & wizards

### 8.1 Dashboard (`/`)
Live MJPEG (5 fps), a "currently tracking" pill driven by `stats` SSE envelopes,
and the last 10 events as thumbnail cards (speed + direction + relative time). An
`EventSource` on `/api/events/stream` prepends new cards in place.

### 8.2 Events (`/events`)
Server-side filtered history: date range, speed range, direction. Keyset
pagination on `ts_utc` desc. `GET /api/events?filters` returns an htmx partial
(card/row list) so filtering and "load more" are partial swaps. Click a card →
modal with the full-frame JPEG. **All timestamps stored UTC, rendered
client-side via `toLocaleString`**; the Pi `TZ` affects logs only. Requires a new
`EventRepo.query(filters, cursor, limit)` method alongside `list_recent`.

### 8.3 CSV export (`GET /api/events.csv?filters`)
Same filtered set, streamed as `text/csv` via a `StreamingResponse` generator
(no in-memory buffering), `Content-Disposition: attachment`. Columns: id,
ts_utc, speed (converted to display units honoring `server.units`), direction,
frame_count, track_len_px, image_path.

### 8.4 Live MJPEG + SSE
- **MJPEG:** `StreamingResponse(media_type="multipart/x-mixed-replace; boundary=frame")`.
  The async generator increments the supervisor viewer count on entry, loops
  read-`latest_frame` → yield multipart chunk → `await asyncio.sleep(0.2)`
  (5 fps), and decrements the viewer count in a `finally` on disconnect
  (`CancelledError`). If `latest_frame` is `None`, yields a small "no signal"
  placeholder JPEG so the `<img>` does not break. `?overlay=1` flips the runner
  into contour-drawing mode for the alignment wizard.
- **SSE:** `text/event-stream`. The generator calls `bus.subscribe()` for its own
  `asyncio.Queue`, loops `await queue.get()`, serializes each `EventEnvelope` as
  an SSE `data:` line with `kind` as the SSE `event:` field
  (`event` | `stats` | `calibration_changed` | `settings_changed`), and emits a
  `: keepalive` comment every ~15 s. `finally` → `bus.unsubscribe(queue)`. This is
  the single fanout point earmarked for v0.2 webhook/MQTT subscribers.
- **Bounded queues / backpressure.** Today `EventBus.subscribe()` hands out an
  **unbounded** `asyncio.Queue` filled via `put_nowait` (`events.py:33,45`), so a
  client that connects and stalls (never reads) would grow its queue without
  limit — a memory-leak vector. MVP-2 changes `subscribe()` to create a
  **bounded** queue (`asyncio.Queue(maxsize=N)`, e.g. N≈100) and `publish` to
  catch `asyncio.QueueFull` per-subscriber: on overflow it drops the oldest entry
  for that subscriber (or drops that envelope) and never raises into the
  publisher. A slow client thus loses events rather than leaking memory or
  stalling the detector thread; delivery to healthy clients is unaffected. This is
  an additive change to `pipeline/events.py` (whose docstring already anticipates
  the SSE consumer).
- The supervisor publishes lightweight `stats` envelopes (~1 Hz: fps, tracking
  flag, uptime) so the dashboard pill and `/api/debug/stats` share one source.

### 8.5 First-run wizard (`/setup`)
Triggered by the first-run gate (no password or no active calibration). Five
linear htmx-swapped steps:
1. **Set admin password** → write `auth.json`, log the session in.
2. **Privacy acknowledgment** — the overall spec §15 "check your local laws"
   screen; single checkbox to proceed.
3. **Pick camera source** (`picamera2:` / `usb:` / `rtsp://` / `file:`) → save
   `camera.source`, `supervisor.restart()`.
4. **Confirm live preview** — embed the MJPEG; "I can see it" advances.
5. **Alignment → Calibration** wizards. Completion = password set + active
   calibration exists, after which the gate stops redirecting.

### 8.6 Alignment wizard (`/setup/align`, also reachable from Settings)
Live MJPEG + transparent `<canvas>` overlay. User drags a rectangle; a "Show
motion-detection overlay" toggle adds `?overlay=1` so they see the actual green
contour boxes through the current crop. Submit → `POST /api/crop` with the rect
in **source-frame coordinates** — the JS scales display→source coords using the
known source resolution before posting (the spec's explicit anti-footgun). Server
validates the rect against frame bounds, writes `detector.crop`,
`supervisor.restart()`.

### 8.7 Calibration wizard (`/setup/calibrate`) — the killer feature (§8.3)
1. `POST /api/calibration/capture` → `supervisor.capture_still()` returns a frozen
   JPEG + its source dimensions.
2. Frozen image in `<img>` + `<canvas>`; user clicks point A and B (red dots,
   connecting line, live pixel-distance label; "undo last point" / "start over").
   Below: real-world distance input + units dropdown (m / ft / in / mm) +
   **direction selector (L2R / R2L)**.
3. `POST /api/calibration/measure` with `{points:[[x,y],[x,y]], distance, units,
   direction}` — **points already scaled to source coords client-side.** Server
   converts distance→mm, computes `mm_per_px = distance_mm / pixel_distance`,
   stores a new active `Calibration` row (snapshotting `reference_points_json` +
   `reference_distance_mm`).
4. **Confirm + verify.** Result shown; the user drives a known-speed vehicle past;
   SSE pushes the next 3 events with a "verify mode" badge. "Looks right"
   finalizes; "Off, try again" loops to step 1.

**Two-scale handling.** A single measurement yields one scale. Each `measure`
submission sets the scale for the chosen `direction`; the other direction defaults
to the same value until separately calibrated. After the first save the wizard
prompts "calibrate the other direction" for users who want per-lane accuracy. See
§9 for why per-direction scales are well-motivated for the target geometry.

**Coordinate-scaling caveat (overall spec §8.3).** The canvas is displayed at a
different resolution than the source frame. Click coords MUST be scaled back to
source coords client-side before submission; the server independently validates
that submitted points fall within the captured frame dimensions. Getting this
wrong ships a calibration off by the display/source ratio.

---

## 9. Speed/calibration model — decision & rationale

**Decision:** MVP-2 retains the MVP-1 two-scale scalar model
(`mm_per_px_l2r` / `mm_per_px_r2l`, horizontal-displacement speed in
`detector/calibration.py`). The planar-homography model is **deferred** to a
separate "calibration v2" spec.

**Why two scales are warranted (not merely legacy).** `mm_per_px` is a
perspective quantity — it varies with object distance from the camera. On a
two-way road the two travel directions usually occupy two lanes at two depths, so
one scale per direction captures the dominant between-lane error.

**Target-geometry analysis (Picam v2, ~30–40 ft from curb, 720p capture).**
Standard v2 lens ≈ 62.2° HFOV → field width `2·d·tan(31.1°)`:

| Distance | Road width in view | mm/px @ 1280w | 25 mph car / frame @15fps |
|---|---|---|---|
| 30 ft | ~36 ft | ~8.6 mm/px | ~87 px |
| 40 ft | ~48 ft | ~11.5 mm/px | ~65 px |

Conclusions:
- **Spatial pixel resolution is not the bottleneck.** 65–87 px/frame (hundreds of
  px over a full track) makes ±1 px quantization < 1% error. A car is ~500 px
  long here — easily detected. Raising capture resolution does **not** materially
  improve speed accuracy.
- **Dominant error sources are temporal and geometric:** (1) timestamp accuracy —
  already handled by MVP-1's capture-time `frame_ts` plumbing; (2) perspective
  across the road's depth — at this geometry the near vs far lane differ ~1.5–1.8×
  in mm/px, which is exactly what two scales capture; (3) centroid jitter / motion
  blur (~10–12 px at 25 mph / 10 ms exposure), worse in low light.
- **What two scales cannot fix:** perspective foreshortening *along* a single
  track. Only a homography addresses that, and since pixels are not the limiter,
  the homography (not higher resolution) is the lever that would tighten accuracy
  later.

**Mounting guidance (documentation deliverable):** angle the camera somewhat
*down the road* rather than straight across to flatten the depth gradient, and
calibrate each direction against a reference at that lane's depth.

**Calibration v2 (deferred).** A planar homography `H` (3×3) maps image pixels to
the road ground plane from ≥4 known correspondences; speed becomes
`‖ground(p_last) − ground(p_first)‖ / Δt` — direction-agnostic, continuous in
perspective, handles diagonal motion. It would replace `speed_from_track` + the
`Calibration` dataclass/schema and redesign the calibration wizard, so it is
out of MVP-2 scope and gets its own spec.

---

## 10. Testing

Mirrors the MVP-1 TDD style; ruff + mypy-strict stay green; target ≥85% coverage
on `web/`.

- **Unit:** `auth.py` (hash/verify, cookie + stream-token sign/verify,
  revocation); `units.py` (kph↔mph conversion + formatting); server-side
  point-in-bounds validation for calibration/crop; `EventRepo.query` filter +
  keyset-pagination logic.
- **Integration (FastAPI `TestClient`, `FileReplaySource`-backed `Supervisor`,
  no hardware):**
  - first-run redirect gate (no password / no calibration → 302 `/setup`);
  - login → session cookie → protected route reachable; bad password rejected;
  - `POST /api/calibration/capture` → `measure` → assert the resulting
    `Calibration.mm_per_px_l2r` matches the hand-computed value within tolerance
    (the overall spec's named test);
  - `POST /api/crop` writes `detector.crop` and triggers a restart;
  - settings save: invalid → 422 + inline errors; valid → saved + restart;
  - SSE: finalize a track via the runner → assert the `event` envelope arrives on
    a subscribed client; `settings_changed` arrives after a save;
  - MJPEG: response is `multipart/x-mixed-replace` with a valid leading JPEG;
  - CSV: correct columns + unit conversion honoring `server.units`.
- **One Playwright smoke test** (overall spec §testing): drive `/setup/calibrate`
  against a `FileReplaySource`, click two canvas points at known coords, submit a
  known distance, assert the resulting `mm_per_px_l2r` within tolerance.
- **Concurrency / robustness tests** (from the co-plan review):
  - call `POST /api/calibration/capture` repeatedly while the pipeline runs on a
    `FileReplaySource` → no crash/deadlock, always a valid JPEG (guards the
    `capture_still` snapshot path);
  - fire two `PUT /api/settings` requests in quick succession → app stays stable
    and converges to the last-saved state (guards the restart lock);
  - unit-test the bounded `EventBus` queue: filling a subscriber's queue past
    `maxsize` drops per policy and never raises into `publish` (guards SSE
    backpressure).

---

## 11. Deployment seam (MVP-3 handoff)

`curbcam serve --host --port --config --data-dir` is the single entrypoint;
everything is constructed from `Settings` + the data dir. MVP-3's Docker image
will simply run `curbcam serve`. mDNS, the multi-arch image, and the
three-command install all stay in MVP-3. MVP-2 deliberately ships no Docker/mDNS.

---

## 12. Risks

- **MJPEG encode cost on a Pi.** Mitigated by encoding only when `viewers > 0` or
  overlay is on, and capping the read side at 5 fps.
- **Restart-on-save detection gap (~1–2 s).** Accepted; settings edits are rare.
  `restart()` runs in a threadpool so other clients' streams are not stalled.
- **Thread ↔ asyncio bridge for SSE.** Relies on `bus.bind_loop` being called at
  startup before any `publish_threadsafe`; covered by an integration test.
- **Concurrent restarts.** Two near-simultaneous settings saves could race to
  replace the runner thread. Mitigated by the `Supervisor` restart lock (§4).
- **`capture_still` mid-loop hazard.** Avoided by design — capture reads a
  lock-protected snapshot slot, never signals the loop or opens a second camera
  handle (§4).
- **SSE backpressure / memory leak.** A stalled client could grow an unbounded
  queue. Mitigated by bounded per-subscriber queues with an oldest-drop policy
  (§8.4).
- **First-run gate edge case.** A user who sets a password but abandons the
  wizard before calibrating must still reach the calibration steps. Handled by
  the gate exempting `/setup*`, `/api/calibration/*`, and `/api/crop` from the
  redirect while still requiring a session on those endpoints; covered by an
  integration test.
- **Calibration accuracy ceiling** set by perspective + centroid jitter, not
  pixels (§9). Documented; homography deferred.
- **Single-process blast radius** (detector crash → web down) — unchanged from the
  overall spec's accepted risk (§14).

---

## 13. Open questions

None blocking. The implementation plan will pin specifics (MJPEG boundary framing
details, exact keyset-pagination cursor encoding, Argon2 cost parameters).
