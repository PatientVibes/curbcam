# Contributing to curbcam

Thanks for looking at this. curbcam is a speed camera you point at your own
street, so the bar for "does it work" is unusually literal: someone drives past,
and the number is either right or it isn't.

## Getting set up

```bash
git clone https://github.com/PatientVibes/curbcam
cd curbcam
uv sync --extra dev --frozen
uv run --frozen pytest
```

You do **not** need a Raspberry Pi or a camera. The test suite runs against a
file-replay camera source, and you can develop the whole web UI the same way:

```bash
uv run --frozen curbcam serve --camera file:./fixtures/sample_run
```

### The `--frozen` rule

**Always pass `--frozen` to both `uv sync` and `uv run`.** The committed
`uv.lock` is resolved *with* the Pi-only `picamera2` extra, so every dependency
carries a `sys_platform` marker. Re-resolving on a non-Pi machine strips those
markers across ~130 entries and degrades the arm64 image.

`uv run` re-locks **by default**, which is the usual source of surprise
`uv.lock` churn — and a dirty lock will block `git checkout`. If it happens:
`git checkout uv.lock`.

Never run `uv sync --all-extras`: `picamera2` pulls `python-prctl`, which needs
libcap headers and fails outright on x86_64. There is no reason to install it
off-Pi.

## Gates

CI runs these on Python 3.12 and 3.13. Run them before pushing:

```bash
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy src/curbcam        # strict
uv run --frozen pytest
```

Plus a Docker amd64 build-and-smoke and an emulated arm64 picamera build-check.

**One CI quirk worth knowing when reviewing dependency PRs:** the `release` and
`picamera-release` jobs in `docker.yml` are gated on `v*` tags, so they **skip on
pull requests**. A green PR therefore does not validate anything used only by the
release path — notably `docker/login-action` and `docker/metadata-action`. A bump
to either can pass every check and still break the first real tag push.

## Adding a setting

curbcam is meant to be configurable without editing YAML or code. A new setting
needs three coordinated edits:

1. `src/curbcam/config/schema.py` — the Pydantic field
2. `src/curbcam/config/defaults.py` — a `(label, help)` row in `FIELD_LABELS`
3. `src/curbcam/web/settings_form.py` — the key and input kind in `PRIMARY`,
   `ADVANCED` or `ALERTS`

Miss (2) and the settings page shows the raw dotted key as the label. Miss (3)
and the field cannot be changed from the UI at all. Both fail
`tests/unit/config/test_settings_ui_coverage.py`, so CI will tell you.

`detector.crop` is the one deliberate exemption — it is set by dragging a
rectangle in the alignment wizard, not typed.

**Help text is for the person aiming a camera at a road**, not for a developer.
Say what the setting does, what raising or lowering it trades away, and give a
usable default.

## Adding an alert channel

1. Implement the transport in `src/curbcam/alerts/channels.py`
2. Add its settings fields per "Adding a setting" above
3. Add a `ChannelSpec` to `src/curbcam/alerts/registry.py`
4. Wire the send in `AlertDispatcher.send_to_channel`

The dispatcher, the settings page's test buttons and `/api/alerts/test/{channel}`
all iterate `CHANNELS`, so a registered channel gets dispatch and a test button
automatically.

## Design docs

Code comments cite two specs by short name:

| Cited as | File |
|---|---|
| **design spec** | `docs/specs/2026-05-28-curbcam-design.md` |
| **web spec** | `docs/specs/2026-05-28-curbcam-mvp-2-web.md` |

Other specs in `docs/specs/` cover the Docker install, the picamera2 image, the
UX uplift, and alerts/reports. They record why things are the way they are;
they are not kept in sync with the code, so treat the code as authoritative when
they disagree.

## Testing conventions

- Unit tests mirror the source tree under `tests/unit/`.
- Integration tests use a file-replay camera and a real `TestClient`
  (`tests/integration/web/conftest.py`).
- `tests/e2e/` is excluded from the default run via `-m 'not e2e'`.
- Two camera tests skip unless you give them hardware: set
  `CURBCAM_TEST_RTSP_URL` or `CURBCAM_TEST_USB_DEVICE`.

**Write the negative case.** A gate that passes on a correct codebase proves
nothing on its own — several tests here exist specifically because the obvious
check turned out to have no teeth. If you add a validation, add the test that
proves it rejects bad input.

## Style

- Python 3.12+, strict mypy over `src/curbcam`.
- Ruff for lint *and* format; formatting is enforced in CI.
- Comments should explain **why**, not what. The codebase leans heavily on this
  — if a line looks odd, the comment should say what breaks without it.
- Reports charts are server-rendered inline SVG. There is deliberately **no
  frontend build step**; please don't introduce one without a strong reason.

## Privacy and responsible use

curbcam records vehicles on a public street. That carries obligations, and they
vary by jurisdiction — see the "Before you install" section of the README and
`SECURITY.md`.

Practical implications for contributions:

- Event images are private and served through an auth-protected route, never as
  static files. Keep it that way.
- The "delete events older than N days" button deletes rows **and** the JPEGs on
  disk. A privacy control that leaves the media behind defeats its purpose.
- Don't add anything that uploads footage off-device by default.

## Pull requests

- One coherent change per PR. Say what breaks without it.
- Include the reasoning in the commit message, not just the what.
- If you find a pre-existing failure while working, say so rather than folding a
  silent fix into an unrelated change.
- New features that are user-visible should update `README.md` and `CHANGELOG.md`.
