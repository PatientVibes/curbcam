# Changelog

Notable user-facing changes to curbcam. Newest first.

## Unreleased

### Added
- **Send a test alert** — each channel has a *Send test to …* button under
  **Settings → Alerts**. It delivers a `[TEST]` message over the real transport,
  so you can confirm an ntfy topic, webhook URL or MQTT broker works without
  waiting for a vehicle to go past. Tests ignore the enable switches, the alert
  speed and the cooldown so you can verify a channel *before* turning it on, and
  a failure shows the actual error (HTTP status, DNS failure, MQTT return code).
- **Backup & restore** — download your settings as YAML from
  **Settings → Backup & restore**, and restore them from a downloaded file. The
  export deliberately excludes your calibration (it is specific to where the
  camera is pointed; restoring it onto a differently-aimed camera would give
  confident but wrong speeds) and excludes your password and stream tokens. It
  may contain an MQTT username/password, so treat the file as sensitive.
- Contributor docs: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue templates and
  a pull-request template.

### Changed
- Settings fields held read-only by a `CURBCAM_*` environment variable now name
  the variable and explain how to unset it, instead of showing an unexplained
  "set via environment" badge.

### Fixed
- CI installed dev tools without using `uv.lock`, so it tracked the newest
  release of ruff/mypy/pytest rather than the reviewed versions. A ruff release
  that began formatting Markdown turned the build red on an unrelated docs
  change. CI now installs with `uv sync --frozen`.
- Reports histogram now buckets in your display units (clean 5 mph / 5 kph bins).
- Daily-volume trend includes zero-event days so the time axis isn't compressed.
- Camera discovery no longer breaks the web app's import on non-Linux machines.

### Added (earlier in this cycle)
- **Alerts** — push a notification when a vehicle is detected at or above a speed
  you choose, via **ntfy** (phone push), a generic **webhook**, or **MQTT** (e.g.
  Home Assistant). Each channel has its own cooldown. Configure under
  **Settings → Alerts**. ntfy topics on the public server are readable by anyone
  who knows the name — pick an unguessable one.
- **Reports** dashboard — vehicle count, median / 85th-percentile / max speed, and
  inline-SVG charts (speed distribution, traffic by hour of day, daily volume
  trend, per-direction breakdown) over a selectable window (Today / 7d / 30d / All).
- **Timezone** setting (**Settings → Timezone**, an IANA name like
  `America/New_York`) — Reports hour-of-day, daily totals, the *Today* window, and
  alert times use it; blank means UTC. The live event feed uses the browser's clock.
- Raspberry Pi Camera Module Docker image (`:picamera`), camera auto-detect in the
  setup wizard, and an admin login on the setup page.
