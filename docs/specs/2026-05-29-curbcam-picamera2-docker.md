# curbcam — Pi Camera Module in Docker (`:picamera` image) — Design Spec

- **Date:** 2026-05-29
- **Status:** Approved (co-planned with Gemini 2.5 Pro; 2 review passes)
- **Owner:** PatientVibes
- **Follows:** `docs/specs/2026-05-29-curbcam-mvp-3-docker-install.md` (this un-defers its §2.2).
  Depends on the MVP-3 artifacts (`Dockerfile`, `docker-entrypoint.sh`, `.github/workflows/docker.yml`)
  having merged first.

## 1. Background & Goal

MVP-3 shipped a three-command Docker install whose multi-arch `:latest` image supports USB, RTSP, and
file-replay cameras. The **Raspberry Pi Camera Module (picamera2/libcamera)** was explicitly deferred
(MVP-3 §2.2): apt's `python3-picamera2` is built against the distro's Python and links a specific
`numpy`/`libcamera` ABI, which collided with MVP-3's `python:3.12-slim-bookworm` base.

**Goal:** ship a dedicated **arm64-only** image `ghcr.io/patientvibes/curbcam:picamera` that runs the
Pi Camera Module through the same curbcam app and the same `docker compose` install, so Pi-cam users
are first-class. **The existing multi-arch `:latest` image is not touched.**

## 2. Scope

### 2.1 In scope
- `Dockerfile.picamera` — a separate, arm64-only image.
- `docker-compose.picamera.yml` — the Pi-cam install overlay.
- CI: an arm64 build-check on PRs and a build-and-push of `:picamera` (+ `:picamera-vX.Y.Z`) on `v*` tags.
- A Python **3.13** leg added to the existing `gates` test matrix.
- README + design-spec doc updates.

### 2.2 Out of scope / non-goals
- Any change to the main `Dockerfile`, the `:latest` multi-arch image, or its CI smoke test.
- Any change to `requires-python = ">=3.12"` (3.13 satisfies it) or to curbcam application code —
  `camera/picamera2_source.py` already lazy-imports picamera2.
- Pinning exact libcamera/picamera2 versions (the image tracks the RPi archive); revisit if drift bites.
- Pre-flashed SD image, ALPR, multi-camera — unchanged from the design spec's deferred list.

## 3. Why a separate, arm64-only image

The Raspberry Pi apt archive ships only `arm64`/`armhf` packages, so this image **cannot** be built for
`amd64` — it is inherently single-arch. Folding an arch-conditional libcamera stack into the unified
`Dockerfile` would mean a different base image per architecture (not cleanly expressible in one
Dockerfile) and would bloat/slow the amd64 build. A separate `Dockerfile.picamera` → a distinct
`:picamera` tag keeps the main image simple and fast and isolates all of this complexity. (Co-plan
CRITICAL/IMPORTANT findings drove this and the choices in §4.)

## 4. The image — `Dockerfile.picamera`

### 4.1 Base + Python (the ABI decision)

Base on **`debian:trixie-slim`** and run curbcam on the **distro's own `python3` (Debian Trixie =
Python 3.13)**. This is the crux: apt's `python3-picamera2` / `python3-libcamera` C-extensions are
compiled against the *distro* Python and the *distro* `python3-numpy`. Using the distro interpreter
guarantees a matching `cp313` ABI. The official `python:3.13` image's separately-built CPython was
rejected as an avoidable ABI gamble (co-plan round 1, CRITICAL). curbcam's `requires-python>=3.12`
already allows 3.13; **only this image runs on 3.13**, no project-wide change.

### 4.2 Raspberry Pi apt archive (mandatory)

Add `archive.raspberrypi.com/debian` (trixie suite) via a `signed-by` keyring. Debian's own `libcamera`
is 0.4 and **lacks the Raspberry Pi camera pipeline**; the RPi archive supplies 0.7 with the hardware
drivers. Without this the camera will not enumerate.

### 4.3 The dependency model — all C-extensions from apt (the correctness core)

Every Python package with a compiled C-extension that links `numpy` — `numpy`, `opencv`, `libcamera`,
`picamera2` — **must come from `apt`**, so they all share one consistent `numpy` ABI. Installing any of
these from PyPI into the same interpreter re-introduces the `numpy.ndarray size changed` ABI break
(co-plan round 2, two CRITICALs: the same risk applies to both picamera2 *and* opencv).

- `apt install python3-picamera2 python3-opencv python3-kms++ libcamera-ipa python3-venv`
  (+ `libglib2.0-0 libgomp1 tini`). `python3-picamera2` pulls `python3-libcamera` and `python3-numpy`
  transitively, so those are not listed explicitly. `libcap-dev` is **not** needed (it only builds
  `python-prctl` from source, which never happens here — picamera2 is apt-provided, not pip).
- Create the app environment with stdlib **`python3 -m venv --system-site-packages /venv`** (NOT
  `uv venv` — uv's environments are isolated and would not see the apt packages; confirmed against uv's
  documented behavior). The venv therefore sees apt's `numpy`, `cv2`, `picamera2`, `libcamera`.
- Install `uv` into the build, then install **only curbcam's pure-Python dependency closure** from the
  wheel — **excluding `numpy` and `opencv-python-headless`** so PyPI never shadows the apt C-stack. The
  remaining wheel deps (fastapi, uvicorn[standard], jinja2, python-multipart, itsdangerous,
  argon2-cffi, pydantic, pydantic-settings, pyyaml, sqlalchemy, alembic, typer, structlog, zeroconf)
  are pure-Python and install cleanly into the venv. The `[picamera2]` pip extra is **not** installed.

  **Mechanism (to lock + verify during implementation):** the preferred approach is to compile the
  wheel's dependency list, strip `numpy` and `opencv-python-headless`, `uv pip install` that list, then
  `uv pip install --no-deps` the curbcam wheel itself. A constraint file pinning `numpy`/`opencv` to the
  apt versions is the fallback. The exact recipe is an implementation detail; §4.5 makes it
  build-time-verifiable so an error fails the build rather than the Pi.

### 4.4 Reused, unchanged from MVP-3

Builder stage builds the same pure-Python curbcam wheel as the main image (curbcam has no compiled
extensions, so the wheel is interpreter-agnostic) — though on a `debian:trixie-slim` + `uv`-binary
builder rather than the main image's `python:3.12-slim-bookworm`, and it additionally exports the
locked runtime deps (minus numpy/opencv) from `uv.lock` for the §4.3 install. Runtime copies `alembic.ini` + `migrations/` +
`docker-entrypoint.sh`; same `db upgrade` → `serve --port 8080 …` entrypoint, same `HEALTHCHECK`, runs
as root, `tini` as PID 1. The config default camera source is already `picamera2:0`, so a fresh install
works on a Pi cam with no extra configuration.

### 4.5 Build-time ABI assertion

The final image includes a build step that runs `python -c "import numpy, cv2, picamera2, libcamera"`
(and prints `numpy.__version__`). If the dependency model produced an ABI mismatch, **the image build
fails** — moving the failure off the user's Pi and into CI. This is the single most important guardrail
given there is no camera in CI.

## 5. Compose — `docker-compose.picamera.yml`

Mirrors the main MVP-3 compose (`network_mode: host`, `init: true`, volumes `./data:/data`,
`./media:/media`, `/run/udev:/run/udev:ro`, `env_file` optional, `TZ`) with `image:
ghcr.io/patientvibes/curbcam:picamera`.

**Device access:** `privileged: true` is the **recommended, documented setting** for Pi Camera Module
access — libcamera enumerates many device nodes (`/dev/dma_heap`, multiple `/dev/video*`/`/dev/media*`,
`/dev/vchiq`, `/dev/vcsm-cma`) and a minimal device list is a common source of "camera not found"
frustration (co-plan IMPORTANT). For users who want least privilege, the file includes a
commented-out **scoped `devices:` alternative** listing those nodes, with a note that it is
best-effort and may need adjustment per Pi model/kernel.

## 6. CI/CD — extend `.github/workflows/docker.yml`

- **On PR:** an arm64-only **build-check** of `Dockerfile.picamera` (`docker/setup-qemu-action` +
  buildx, `platforms: linux/arm64`, no `push`, no run). Catches a broken RPi-archive/apt/venv chain and
  trips the §4.5 import assertion before any tag. Emulated arm64 + RPi-archive apt is slow (~10 min) but
  only adds one job.
- **On `v*` tags:** build + push `:picamera` and `:picamera-vX.Y.Z` (arm64-only) to GHCR, alongside the
  existing multi-arch `:latest`/`:vX.Y.Z` release. **Build-only — no smoke test** (emulated arm64, no
  camera). `provenance: false` for older-Docker-on-Pi compatibility, consistent with MVP-3.
- **Test matrix:** add Python **3.13** to the existing `gates` job in `ci.yml`, so curbcam's own code
  and tests are proven on the interpreter the `:picamera` image runs — independent of any hardware.

## 7. Docs

- **README:** a "Pi Camera Module (Docker)" subsection pointing at the `:picamera` tag +
  `docker-compose.picamera.yml`, the `privileged`-recommended / scoped-alternative guidance, and the
  "verify on a Pi" expectation. The MVP-3 "picamera not yet supported in Docker" note is replaced.
- **Design spec** (`2026-05-28-curbcam-design.md` §13.2/§14) and **MVP-3 spec** (§2.2): flip
  picamera2-in-Docker from "deferred" to "supported via the `:picamera` image," referencing this spec.

## 8. Risks

- **The `numpy`/opencv ABI model is the primary risk.** Mitigated by sourcing the whole C-stack from
  apt (§4.3) and the build-time import assertion (§4.5). The exact uv install recipe is verified at
  build time, not on the Pi.
- **arm64-under-QEMU build** with RPi-archive apt: slow and occasionally flaky (network/emulation).
  Acceptable; the build-check is one extra job and the release path runs only on tags.
- **Trixie/3.13 + RPi-archive package availability:** `debian:trixie-slim` ships Python 3.13 (verified:
  packages.debian.org) and the RPi trixie archive carries `python3-picamera2`; confirm exact package
  set during implementation.
- **No camera in CI** → the camera path is unprovable in CI. Mandatory manual Pi verification (§9).
- **apt version drift** (no pin) → note pinning as a future option if a bad upstream lands.
- **`privileged`** grants broad host access on a device that captures public imagery — acceptable on a
  dedicated single-purpose Pi (documented), with the scoped alternative for the security-conscious.

## 9. Verification

- **CI:** the arm64 `Dockerfile.picamera` build succeeds (PR build-check / tag build+push), **including
  the §4.5 `import numpy, cv2, picamera2, libcamera` assertion** — this is the de-facto ABI gate.
- `ci.yml` gates pass on Python **3.12 and 3.13**.
- **Manual (mandatory, not CI):** on a Raspberry Pi (Trixie or Bookworm) with a Camera Module:
  `docker compose -f docker-compose.picamera.yml up -d` → browse `http://curbcam.local:8080` → the live
  preview shows the Pi camera and the calibration wizard completes. `docker exec <ctr> python -c
  "import picamera2"` succeeds.

## 10. Open Questions

- The exact `uv` recipe for "pure-Python deps only" (strip-and-`--no-deps` vs constraint file) is left
  to the implementation plan; §4.5 makes either choice self-verifying at build time.
