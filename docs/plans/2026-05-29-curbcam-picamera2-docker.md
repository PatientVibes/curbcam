# curbcam — Pi Camera Module in Docker (`:picamera` image) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a dedicated, **arm64-only** `ghcr.io/patientvibes/curbcam:picamera` image so Raspberry Pi Camera Module users get the same Docker install as USB/RTSP users, without touching the main multi-arch `:latest` image.

**Architecture:** A separate `Dockerfile.picamera` on `debian:trixie-slim` running curbcam on the distro's own Python 3.13. The entire numpy-linked C-extension stack (`numpy`, `opencv`, `libcamera`, `picamera2`) is installed from `apt` (the Raspberry Pi archive for libcamera 0.7) so they share one consistent numpy ABI; curbcam + its pure-Python deps install from the wheel into a `python3 -m venv --system-site-packages`, with `numpy`/`opencv-python-headless` excluded. A build-time `import numpy, cv2, picamera2, libcamera` assertion turns any ABI mismatch into a build failure (no camera in CI). A new arm64 CI job build-checks on PRs and build-pushes `:picamera` on `v*` tags.

**Tech Stack:** Docker (multi-stage, buildx + QEMU for arm64), Debian Trixie, Python 3.13, `uv`, the Raspberry Pi apt archive, GitHub Actions, GHCR.

**Reference:** Spec at `docs/specs/2026-05-29-curbcam-picamera2-docker.md` (cited §N). Depends on the MVP-3 artifacts (`Dockerfile`, `docker-entrypoint.sh`, `.github/workflows/docker.yml`, `docker-compose.yml`) — this branch is stacked on the MVP-3 branch, so they are present. Plan style: `docs/plans/2026-05-29-curbcam-mvp-3-docker-install.md`.

---

## Prerequisite note

This plan **must be implemented on top of MVP-3** (branch `docs/mvp-3-docker-install` / PR #30). It
reuses `docker-entrypoint.sh`, `alembic.ini`, `migrations/`, the `.github/workflows/docker.yml`
workflow, and references the existing `docker-compose.yml`. If MVP-3 has merged to `main`, branch from
`main`; otherwise stack on the MVP-3 branch (already done: `docs/picamera2-docker`).

## File Structure

```
Dockerfile.picamera                 # arm64-only image (debian:trixie + RPi archive + apt C-stack)
docker-compose.picamera.yml         # Pi-cam install overlay (privileged recommended)
.github/workflows/docker.yml        # MODIFY: add arm64 build-check (PR) + :picamera push (tag)
.github/workflows/ci.yml            # MODIFY: add Python 3.13 to the gates matrix
README.md                           # MODIFY: "Pi Camera Module (Docker)" section
docs/specs/2026-05-28-curbcam-design.md            # MODIFY: §13.2/§14 un-defer
docs/specs/2026-05-29-curbcam-mvp-3-docker-install.md  # MODIFY: §2.2 un-defer note
```

No application/Python source changes — `src/curbcam/camera/picamera2_source.py` already lazy-imports
picamera2 and is unchanged.

---

## Task 1: Prove curbcam runs on Python 3.13 (gates matrix)

This de-risks the whole premise (the `:picamera` image runs curbcam on 3.13) cheaply and first, and is
the only locally/CI-testable Python surface in this plan.

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Verify the suite passes on 3.13 locally (TDD-style: this is the failing/passing check)**

`uv` can fetch 3.13 even on a 3.12 dev box:

```bash
cd D:/curbcam
uv python install 3.13
uv venv --python 3.13 .venv-313
uv pip install --python .venv-313 -e ".[dev]"
uv run --python .venv-313 pytest -q
```

Expected: the full suite passes on 3.13 (same as 3.12). If a real 3.13 incompatibility surfaces in
curbcam's own code, STOP and report it — that would be a finding that affects the whole picamera
premise, not a mechanical fix. (None is expected; the code is plain 3.12+ typing.) Clean up:
`rm -rf .venv-313`.

- [ ] **Step 2: Read the current `ci.yml` gates job**

```bash
sed -n '1,60p' .github/workflows/ci.yml
```

It currently installs `--python 3.12` in a single `gates` job (no matrix).

- [ ] **Step 3: Add a Python matrix to the `gates` job**

Edit `.github/workflows/ci.yml` so the `gates` job runs a matrix over 3.12 and 3.13. Change the job to:

```yaml
  gates:
    name: gates (py${{ matrix.python }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python: ["3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v6

      - name: Create venv + install (dev extras)
        run: |
          uv venv --python ${{ matrix.python }}
          uv pip install -e ".[dev]"

      - name: Ruff lint
        run: uv run --no-sync ruff check .

      - name: Ruff format check
        run: uv run --no-sync ruff format --check .

      - name: Mypy (strict)
        run: uv run --no-sync mypy src/curbcam

      - name: Tests (e2e excluded via addopts -m 'not e2e')
        run: uv run --no-sync pytest -q
```

(Preserve the file's existing `name:`, `on:`, `permissions:`, and `concurrency:` blocks above the job.)

- [ ] **Step 4: Validate the workflow YAML**

```bash
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('yaml OK')"
```

Expected: `yaml OK`.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run gates on Python 3.12 and 3.13 (picamera image runs 3.13)"
```

---

## Task 2: `Dockerfile.picamera`

The image. The build-time import assertion (Step 1's final `RUN`) is the test: if the apt-vs-pip ABI
model is wrong, the build fails here, in CI, not on a user's Pi (spec §4.5).

**Files:**
- Create: `Dockerfile.picamera`

- [ ] **Step 1: Write `Dockerfile.picamera`**

```dockerfile
# syntax=docker/dockerfile:1
# Raspberry Pi Camera Module (picamera2) image — arm64 ONLY.
# The Raspberry Pi apt archive has no amd64 packages, so this image cannot
# build for amd64. See docs/specs/2026-05-29-curbcam-picamera2-docker.md.

# ---- builder: wheel + a pure-Python-only requirements list ----
FROM debian:trixie-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /build
COPY pyproject.toml README.md uv.lock ./
COPY src ./src
# Build the (pure-Python) curbcam wheel.
RUN uv build --wheel --out-dir /wheels
# Resolve the full runtime dependency closure for Python 3.13, then strip the
# two C-extension packages that MUST instead come from apt (numpy, opencv) so
# they share the apt libcamera/picamera2 numpy ABI (spec §4.3). opencv-python-
# headless's only dependency is numpy, so removing both lines leaves no orphans.
RUN uv pip compile pyproject.toml --python-version 3.13 -o /wheels/requirements.txt \
    && sed -i -E '/^(numpy|opencv-python-headless)([=<>!~; ]|$)/d' /wheels/requirements.txt

# ---- runtime: debian:trixie (distro python3 == 3.13) + RPi libcamera stack ----
FROM debian:trixie-slim AS runtime
# Add the Raspberry Pi apt archive (libcamera 0.7 with the Pi camera pipeline;
# Debian's own libcamera 0.4 lacks it — spec §4.2), then install the entire
# numpy-linked C-extension stack from apt so it shares one consistent ABI.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -fsSL https://archive.raspberrypi.org/debian/raspberrypi.gpg.key \
        | gpg --dearmor -o /usr/share/keyrings/raspberrypi-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/raspberrypi-archive-keyring.gpg] https://archive.raspberrypi.com/debian trixie main" \
        > /etc/apt/sources.list.d/raspberrypi.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-venv \
        python3-picamera2 python3-opencv python3-kms++ libcamera-ipa \
        libglib2.0-0 libgomp1 tini \
    && apt-get purge -y curl gnupg \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# A venv that can see the apt-installed numpy/opencv/picamera2/libcamera.
RUN python3 -m venv --system-site-packages /venv
ENV PATH="/venv/bin:$PATH"

# Install curbcam's pure-Python deps (numpy/opencv stripped) + curbcam itself
# (--no-deps so the wheel's numpy/opencv requirements are not pulled from PyPI).
COPY --from=builder /wheels/ /tmp/wheels/
RUN uv pip install --python /venv/bin/python -r /tmp/wheels/requirements.txt \
    && uv pip install --python /venv/bin/python --no-deps /tmp/wheels/curbcam-*.whl \
    && rm -rf /tmp/wheels

# Build-time ABI assertion (spec §4.5): the whole image is invalid if these do
# not import together on one numpy ABI. Fails the build, not the user's Pi.
RUN /venv/bin/python -c "import numpy, cv2, picamera2, libcamera; print('numpy', numpy.__version__)"

# Alembic config + migrations + entrypoint (reused from MVP-3, unchanged).
WORKDIR /app
COPY alembic.ini ./
COPY migrations ./migrations
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/healthz').status == 200 else 1)"

ENTRYPOINT ["tini", "--", "/docker-entrypoint.sh"]
```

- [ ] **Step 2: Verify the Raspberry Pi archive key URL resolves (cheap pre-flight)**

```bash
curl -fsSL https://archive.raspberrypi.org/debian/raspberrypi.gpg.key | head -c 64 && echo " ...(key fetched)"
```

Expected: a PGP key blob is fetched (no 404). If this URL has moved, update the `Dockerfile.picamera`
`curl` line to the current key location before proceeding. (The archive host for packages is
`archive.raspberrypi.com`; the key has historically been served from `archive.raspberrypi.org`.)

- [ ] **Step 3: (Optional) local arm64 build if buildx+QEMU is available**

This image is arm64-only and **cannot** build for amd64 (no RPi amd64 packages), so a local build needs
QEMU. If `docker buildx` + QEMU are set up:

```bash
docker run --privileged --rm tonistiigi/binfmt --install arm64    # one-time QEMU setup
docker buildx build --platform linux/arm64 -f Dockerfile.picamera -t curbcam:picamera-local .
```

Expected: the build completes through the `import numpy, cv2, picamera2, libcamera` assertion (prints a
numpy version). **If buildx/QEMU is not available, SKIP** — Task 4's CI build-check is the real gate.
If the build fails at the import assertion, the dependency model needs adjustment (the most likely
fix: the `sed` strip pattern, or an additional apt package); report the exact error.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile.picamera
git commit -m "build(docker): Dockerfile.picamera — arm64 Pi Camera image (apt C-stack, ABI assert)"
```

---

## Task 3: `docker-compose.picamera.yml`

**Files:**
- Create: `docker-compose.picamera.yml`

- [ ] **Step 1: Write `docker-compose.picamera.yml`**

```yaml
# Raspberry Pi Camera Module install. Uses the arm64-only :picamera image.
# Usage: docker compose -f docker-compose.picamera.yml up -d
services:
  curbcam:
    image: ghcr.io/patientvibes/curbcam:picamera
    restart: unless-stopped
    # REQUIRED: mDNS multicast (curbcam.local) cannot cross the Docker bridge
    # NAT, so the container shares the host network (publishes 8080 directly).
    network_mode: host
    init: true
    # RECOMMENDED for the Pi Camera Module: libcamera enumerates many device
    # nodes; privileged is the reliable, supported path on a dedicated Pi.
    privileged: true
    volumes:
      - ./data:/data
      - ./media:/media
      - /run/udev:/run/udev:ro
    # Least-privilege ALTERNATIVE to `privileged: true` (advanced users):
    # comment out `privileged: true` above and uncomment the block below. This
    # is best-effort and may need adjustment per Pi model / kernel.
    # devices:
    #   - /dev/dma_heap:/dev/dma_heap
    #   - /dev/vchiq:/dev/vchiq
    #   - /dev/vcsm-cma:/dev/vcsm-cma
    #   - /dev/video0:/dev/video0
    #   # (libcamera may need additional /dev/video* and /dev/media* nodes)
    env_file:
      - path: .env
        required: false
    environment:
      - TZ=America/Los_Angeles
```

- [ ] **Step 2: Validate the compose file**

```bash
uv run python -c "import yaml; yaml.safe_load(open('docker-compose.picamera.yml')); print('yaml OK')"
```

Expected: `yaml OK`. If `docker compose` is available locally, also run
`docker compose -f docker-compose.picamera.yml config -q` (expect success / no output).

- [ ] **Step 3: Commit**

```bash
git add docker-compose.picamera.yml
git commit -m "build(docker): docker-compose.picamera.yml (privileged, host net, :picamera)"
```

---

## Task 4: CI — arm64 build-check (PR) + `:picamera` push (tag)

**Files:**
- Modify: `.github/workflows/docker.yml`

- [ ] **Step 1: Read the current workflow to anchor the edits**

```bash
sed -n '1,120p' .github/workflows/docker.yml
```

It has a `build-smoke` job (PR + push + tags) and a tag-gated `release` job. You will ADD two things:
a `picamera-build-check` job (PR) and a `picamera-release` job (tags). Do not modify the existing jobs.

- [ ] **Step 2: Add the picamera build-check job (runs on PR + push, arm64, no push)**

Append this job under `jobs:` in `.github/workflows/docker.yml`:

```yaml
  picamera-build-check:
    name: picamera arm64 build-check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: docker/setup-qemu-action@v3

      - uses: docker/setup-buildx-action@v3

      - name: Build arm64 picamera image (no push)
        uses: docker/build-push-action@v6
        with:
          context: .
          file: Dockerfile.picamera
          platforms: linux/arm64
          push: false
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

This exercises the RPi-archive apt install + venv + wheel install + the build-time import assertion
under emulated arm64. It does not run the container (no camera, emulated arch). It is slow (~10 min);
that is acceptable for one job.

- [ ] **Step 3: Add the picamera release job (tags only, arm64, push)**

Append this job too:

```yaml
  picamera-release:
    name: picamera arm64 release -> GHCR
    if: startsWith(github.ref, 'refs/tags/v')
    needs: picamera-build-check
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

      - name: Image metadata (picamera tags)
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/patientvibes/curbcam
          tags: |
            type=raw,value=picamera
            type=semver,pattern=picamera-v{{version}}

      - name: Build + push arm64 picamera image
        uses: docker/build-push-action@v6
        with:
          context: .
          file: Dockerfile.picamera
          platforms: linux/arm64
          push: true
          provenance: false
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

- [ ] **Step 4: Validate the workflow YAML + confirm job structure**

```bash
uv run python -c "import yaml; d=yaml.safe_load(open('.github/workflows/docker.yml')); print(sorted(d['jobs']))"
```

Expected: the printed job list includes `build-smoke`, `release`, `picamera-build-check`,
`picamera-release` (the first two unchanged).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/docker.yml
git commit -m "ci(docker): arm64 :picamera build-check on PR + push on v* tags"
```

---

## Task 5: Docs — README + spec un-defer

**Files:**
- Modify: `README.md`
- Modify: `docs/specs/2026-05-29-curbcam-mvp-3-docker-install.md`
- Modify: `docs/specs/2026-05-28-curbcam-design.md`

- [ ] **Step 1: Update `README.md`**

In the "Cameras in Docker" note (added in MVP-3, which currently says the Pi Camera Module is not yet
supported in Docker), replace the "not yet supported" sentence with a pointer to the new image, and add
a short subsection. Concretely, change the cameras note to:

```markdown
**Cameras in Docker:** USB (`usb:0`), RTSP (`rtsp://…`), and file replay run on the standard
multi-arch image. The **Raspberry Pi Camera Module** runs on a dedicated arm64 image — see below.
Keep RTSP credentials in a gitignored `.env` (see `.env.example`) rather than in `curbcam.yaml`.
```

And add this subsection right after the "Install (Docker)" section:

```markdown
### Raspberry Pi Camera Module

The Pi Camera Module (libcamera/picamera2) runs on a dedicated **arm64-only** image,
`ghcr.io/patientvibes/curbcam:picamera`, with its own compose file:

```bash
mkdir curbcam && cd curbcam
curl -O https://raw.githubusercontent.com/PatientVibes/curbcam/main/docker-compose.picamera.yml
docker compose -f docker-compose.picamera.yml up -d
# browse to http://curbcam.local:8080
```

This image bases on Debian Trixie and installs libcamera + picamera2 from the Raspberry Pi apt
archive. It runs `privileged: true` by default — the reliable path for camera device access on a
dedicated Pi. Advanced users can switch to a scoped device list (commented in the compose file) and
accept the extra setup. Requires a 64-bit Raspberry Pi OS.
```

- [ ] **Step 2: Un-defer in the MVP-3 spec**

In `docs/specs/2026-05-29-curbcam-mvp-3-docker-install.md` §2.2, append to the picamera2 deferral
paragraph:

```markdown

**Update (2026-05-29):** no longer deferred — Pi Camera Module support ships as a dedicated arm64
`:picamera` image; see `docs/specs/2026-05-29-curbcam-picamera2-docker.md`.
```

- [ ] **Step 3: Un-defer in the design spec**

In `docs/specs/2026-05-28-curbcam-design.md`, update the picamera2-in-Docker lines in §13.2 (Deferred)
and §14 (Risks) to note it is now supported via the `:picamera` image, referencing
`docs/specs/2026-05-29-curbcam-picamera2-docker.md`. Keep the edits surgical (one annotation each); do
not rewrite the sections.

- [ ] **Step 4: Confirm no Python gates broke (docs-only, but verify)**

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
```

Expected: unchanged green (docs edits don't touch Python).

- [ ] **Step 5: Commit**

```bash
git add README.md docs/specs/2026-05-29-curbcam-mvp-3-docker-install.md docs/specs/2026-05-28-curbcam-design.md
git commit -m "docs: Pi Camera Module Docker image — README + un-defer specs"
```

---

## Notes for the implementer

- **This image is arm64-only.** Do not add `linux/amd64` to any picamera buildx step — the RPi archive
  has no amd64 packages and the build will fail. The main `:latest` image remains the amd64/multi-arch one.
- **The build-time `import numpy, cv2, picamera2, libcamera` assertion is the spec's central guardrail
  (§4.5).** If it fails in CI, the dependency model is wrong — do not delete or weaken the assertion to
  make the build pass; fix the model (most likely the `sed` strip in `Dockerfile.picamera`, an extra
  apt package, or sourcing another package from apt).
- **uv reads `pyproject.toml` deps for `uv pip compile`** — when a curbcam dependency is added/removed
  later, the stripped requirements regenerate automatically; only revisit the `sed` line if a *new*
  numpy-linked C-extension dependency is introduced.
- **GHCR image name is lowercase** — `ghcr.io/patientvibes/curbcam`.
- **Camera correctness is unprovable in CI** (no Pi, emulated arch). The mandatory manual Pi
  verification in spec §9 is the real acceptance test — surface it in the PR description.

## Self-Review

**Spec coverage:** §2.1 in-scope → `Dockerfile.picamera` (T2), `docker-compose.picamera.yml` (T3), CI
arm64 build-check + tag push (T4), Python 3.13 gates leg (T1), README + spec un-defer (T5). §3
(separate arm64-only image) → T2/T4. §4.1 base/python → T2. §4.2 RPi archive → T2 + key pre-flight. §4.3
all-C-from-apt + venv + strip-numpy/opencv → T2 builder+runtime. §4.4 reuse entrypoint → T2. §4.5
build-time assertion → T2 Step 1 final RUN + Notes. §5 compose privileged-recommended/scoped-alt → T3.
§6 CI → T1 + T4. §7 docs → T5. §9 verification → T1 Step 1 (3.13 suite), T2 Step 3 (build), T4 (CI),
plus the documented manual Pi test. No gaps.

**Placeholder scan:** none — every file is given in full; the one spec Open Question (exact uv recipe)
is resolved here concretely (compile + `sed` strip + `--no-deps` wheel) and made self-verifying by the
build assertion.

**Consistency:** image name `ghcr.io/patientvibes/curbcam:picamera` and tag pattern `picamera-v{{version}}`
are consistent across T4 and T5; `Dockerfile.picamera` / `docker-compose.picamera.yml` filenames
consistent across all tasks; the `--system-site-packages` venv + `--no-deps` wheel install are stated
identically in T2 and the Notes.

This plan is on branch `docs/picamera2-docker` (stacked on the MVP-3 branch; the spec is already committed there).
