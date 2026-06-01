# Changelog

Notable user-facing changes to curbcam. Newest first.

## Unreleased

### Added
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

### Fixed
- Reports histogram now buckets in your display units (clean 5 mph / 5 kph bins).
- Daily-volume trend includes zero-event days so the time axis isn't compressed.
- Camera discovery no longer breaks the web app's import on non-Linux machines.
