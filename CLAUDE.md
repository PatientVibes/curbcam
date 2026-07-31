# curbcam — agent instructions

A neighbor-friendly speed camera for Raspberry Pi: detect moving vehicles, compute speed, store
events, and expose everything through a web UI with a guided calibration wizard. Runs on a Pi in
production; developed and tested on x86_64.

See [README.md](README.md) for user-facing docs and [`docs/specs/`](docs/specs/) for per-feature
design specs.

## Commands

```bash
uv sync --extra dev --frozen        # install (see the --frozen rule below)

uv run --frozen pytest -q           # 257 tests; e2e excluded by default addopts
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy src/curbcam    # strict

uv run --frozen curbcam serve       # http://localhost:8000
```

CI runs exactly these gates on py3.12 and py3.13, plus a Docker amd64 build-and-smoke and an
emulated arm64 picamera build-check.

## The `uv.lock` rule (read this before touching dependencies)

**Always pass `--frozen`. Never use `--all-extras`.**

The committed `uv.lock` is resolved *with* the Pi-only `picamera2` extra. That makes it a universal
lock: every dependency carries a `sys_platform == 'linux' or sys_platform == 'win32'` marker. Two
consequences:

1. **Re-resolving strips those markers** across ~130 entries. The diff looks like harmless noise but
   it degrades the arm64 Pi build. Never commit it.
2. **`uv run` re-locks by default** — not `uv sync`. This is the usual source of surprise churn, and
   it is easy to miss because the command appears to succeed. A dirty lock then blocks
   `git checkout` / `gh pr checkout` with "local changes would be overwritten".

If the lock does go dirty: `git checkout uv.lock`.

CI installs with `uv sync --extra dev --frozen` and then runs each gate with `uv run --no-sync`, so it
never re-resolves either. **Do not change that back to `uv pip install -e ".[dev]"`** — that ignores
the lockfile and resolves the newest release of every dev tool at run time, which means a ruff, mypy,
or pytest release can turn CI red with no code change. It already happened once: ruff 0.16 started
formatting Python code blocks inside Markdown, which pulled `docs/plans/*.md` and `docs/specs/*.md`
into scope and failed 6 files that predate the rule.

`uv sync --all-extras` additionally **fails outright on x86_64** — `picamera2` pulls `python-prctl`,
which needs libcap development headers. There is no reason to install it off-Pi.

## Layout

```
src/curbcam/
├── camera/      # sources: usb:, rtsp:, file:, picamera2:
├── detector/    # motion detection + speed computation
├── pipeline/    # frame → detection → event orchestration
├── storage/     # SQLite + Alembic migrations
├── web/         # FastAPI app, wizard, dashboard, Events, Reports, Settings
├── alerts/      # ntfy / webhook / MQTT channels
├── discovery/   # mDNS (zeroconf) so curbcam.local resolves
└── config/      # YAML config + env overrides

tests/
├── unit/        # mirrors the src tree
├── integration/ # incl. web/ with fixtures
└── e2e/         # excluded from the default run via addopts -m 'not e2e'
```

## Testing notes

- Two tests **skip by design** unless you give them hardware: set `CURBCAM_TEST_RTSP_URL` or
  `CURBCAM_TEST_USB_DEVICE` to exercise the RTSP and USB camera sources.
- One test is **deselected** by the default `-m 'not e2e'` addopts. Run e2e explicitly if you need it.
- The entrypoint runs Alembic migrations on boot, so container upgrades are safe — the Docker smoke
  test asserts the SQLite file exists afterward.

## CI structure — important when reviewing dependency PRs

`.github/workflows/docker.yml` has four jobs, and **two of them do not run on pull requests**:

| Job | Trigger | Runs on PR? |
|---|---|---|
| `build-smoke` (amd64 + smoke) | always | yes |
| `picamera-build-check` (arm64) | PR or `v*` tag | yes |
| `release` (multi-arch → GHCR) | `v*` tag only | **no** |
| `picamera-release` (→ GHCR) | `v*` tag only | **no** |

So a green PR **does not** validate anything used solely by the release path — notably
`docker/login-action` and `docker/metadata-action`. A dependency bump to either can pass every check
and still break the first real tag push. When bumping those, cut a throwaway tag to exercise the
release path deliberately.

## Conventions

- Python 3.12+ (CI also gates 3.13). Strict mypy over `src/curbcam`.
- Ruff for both lint and format; formatting is enforced in CI.
- Keep RTSP credentials out of `curbcam.yaml` — use a gitignored `.env` (see `.env.example`).
- Reports charts are **server-rendered inline SVG**. There is deliberately no frontend build step;
  do not introduce one without a strong reason.
