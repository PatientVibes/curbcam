# curbcam — Alerts & Reports Design Spec

- **Date:** 2026-06-01
- **Status:** Approved, pending implementation
- **Owner:** PatientVibes
- **Scope:** The two v0.2 features needed to round out the initial release
  ([design spec §13.2](2026-05-28-curbcam-design.md)): threshold **alerts**
  (ntfy + webhook + MQTT) and a **reports** dashboard.

## 1. Background & motivation

Today curbcam's data flow dead-ends: a detected speed lands in SQLite and the
user can scroll the Events feed or export CSV. That makes it a *logging tool*.
These two features close the loop and make it a speed camera worth keeping
running:

- **Alerts** close the *live* loop — "tell me when someone is speeding on my
  street" is the actual job most installs are for. A push notification
  delivers it; passive logging does not.
- **Reports** close the *retrospective* loop — the genre's real payoff is
  *making a case* (to a neighbour, an HOA, the city). A speed histogram +
  by-hour chart is what you screenshot and send.

Both consume data that already exists; neither requires touching the detector
or the camera. The pipeline `EventBus` was explicitly earmarked in the
original design for "future v0.2 webhook/MQTT plugins" — alerts realise that.

## 2. Goals

1. Fire a notification to one or more channels when a vehicle exceeds a
   user-set speed, without spamming during a busy period.
2. All alert config is editable from the Settings UI and overridable via env
   vars (so secrets — webhook URLs, MQTT credentials — can live in `.env`,
   consistent with the existing RTSP pattern).
3. A reports page that turns stored events into an at-a-glance, screenshot-able
   summary over a selectable time window.
4. Zero new frontend build step and no image bytes leaving the device.

## 3. Non-goals (deferred)

- Quiet-hours / do-not-disturb windows.
- Home Assistant MQTT auto-discovery / per-event sensor publishing.
- Channel-specific formatters (Discord/Slack embeds, etc.).
- Alert delivery history persisted in the DB.
- Image attachments in notifications.
- Email/SMS channels.

## 4. Alerts

### 4.1 Architecture

A single **`AlertDispatcher`** runs as an asyncio task started in the app
`lifespan`, structured exactly like the existing `_stats_loop`. It
`subscribe()`s to the `EventBus` and reacts to envelopes:

```
runner thread ── bus.publish_threadsafe("event") ──▶ [asyncio loop]
                                                         ├─▶ SSE generator (existing)
                                                         └─▶ AlertDispatcher  (new)
```

- The detector thread is untouched; the dispatcher is a pure consumer of the
  existing `kind="event"` payload
  (`id`, `speed_kph`, `direction`, `image_path`, `thumb_path`, `ts_utc`).
- **Cached config, refreshed on `settings_changed`.** The dispatcher loads
  `AlertsSettings` once at startup and caches it, then reloads the cache when a
  `kind="settings_changed"` envelope arrives on the bus. Every Settings save
  calls `Supervisor.restart()`, which publishes exactly that envelope — so the
  cache stays live without reading YAML on the event loop per event (which would
  put synchronous file I/O in the asyncio loop's hot path).
- **Lifecycle:** created and cancelled alongside `_stats_loop` in `lifespan`.

### 4.2 Qualifying rule

An event qualifies when:

```
alerts.enabled AND event.speed_kph >= alerts.min_speed_kph
```

`alerts.min_speed_kph` is stored in kph and shown in the user's display units
(like other speed fields). It is independent of `server.min_event_speed_kph`,
which gates whether an event is *recorded* at all; the alert threshold is
expected to be ≥ that, but this is not enforced.

### 4.3 Per-channel cooldown

Each channel carries its own `cooldown_s`. After a channel fires, it is
suppressed until its window elapses; qualifying events in between are dropped
*for that channel only*. Cooldown state is held in-memory on the dispatcher
(`{channel: last_fired_monotonic}`) and resets on restart — acceptable.

`cooldown_s = 0` disables throttling for that channel. This is the mechanism by
which an MQTT / Home-Assistant user receives **every** qualifying event
(`mqtt_cooldown_s = 0`, default) while ntfy/webhook stay quiet
(`cooldown_s = 60`, default).

### 4.4 Channels

All channels send the same logical message; only the transport differs. Each
dispatch is wrapped in try/except so one channel's failure logs a warning and
never affects the others or the loop. HTTP calls use a short `httpx` timeout.

| Channel | Transport | Notes |
|---|---|---|
| **ntfy** | `POST {ntfy_server}/{ntfy_topic}`, body = message text, `Title` + `Click` headers | `Click` = `base_url/events` when `base_url` set. Default server `https://ntfy.sh`. |
| **webhook** | `POST {webhook_url}`, JSON body (§4.5) | Generic; user wires Discord/HA/Zapier/etc. |
| **MQTT** | publish JSON body (§4.5) to `mqtt_topic` | `paho-mqtt`, fire-and-forget, lazy connect + reconnect. New runtime dependency. |

### 4.5 Message content

- **Text (ntfy title/body):** e.g. `"38 mph westbound at 2:14 PM"` — speed in
  user units, human direction, local-time-formatted timestamp. When
  `base_url` is set, a click-through link to `{base_url}/events`.
- **JSON (webhook + MQTT):**
  ```json
  {
    "event_id": 123,
    "speed_kph": 61.2,
    "speed_display": 38.0,
    "units": "mph",
    "direction": "L2R",
    "ts_utc": "2026-06-01T19:14:02",
    "url": "http://curbcam.local:8080/events"
  }
  ```
- **No image bytes leave the device.** Only a link to the auth-gated event view
  is ever included — preserving the project's privacy stance (§15 of the
  original design).

### 4.6 Config model

New `AlertsSettings` block in `config/schema.py`, mounted on `Settings` as
`alerts`. Env-overridable for free via the existing
`CURBCAM_ALERTS__<FIELD>` mechanism.

| Field | Type | Default |
|---|---|---|
| `enabled` | bool | `false` |
| `min_speed_kph` | float ≥ 0 | `0` |
| `base_url` | str | `"http://curbcam.local:8080"` |
| `ntfy_enabled` | bool | `false` |
| `ntfy_server` | str | `"https://ntfy.sh"` |
| `ntfy_topic` | str | `""` |
| `ntfy_cooldown_s` | int ≥ 0 | `60` |
| `webhook_enabled` | bool | `false` |
| `webhook_url` | str | `""` |
| `webhook_cooldown_s` | int ≥ 0 | `60` |
| `mqtt_enabled` | bool | `false` |
| `mqtt_host` | str | `""` |
| `mqtt_port` | int | `1883` |
| `mqtt_topic` | str | `"curbcam/events"` |
| `mqtt_username` | str | `""` |
| `mqtt_password` | str | `""` |
| `mqtt_cooldown_s` | int ≥ 0 | `0` |

A channel fires only when both `alerts.enabled` and its own `<chan>_enabled`
are true and its required target (topic/url/host) is non-empty. `base_url`
blank → omit the click link.

### 4.7 UI

A new **"Alerts" fieldset** added to the existing flat settings form via
`settings_form.py` (`PRIMARY`/`ADVANCED` gain a third group `ALERTS`) and
`config/defaults.FIELD_LABELS`. Env-shadowed fields render read-only exactly
as today. No conditional show/hide JS for v1 — flat fields match the current
pattern. **Boolean fields render as a `select:true,false`** (reusing the
existing select kind), *not* checkboxes: a `<select>` always submits a value,
whereas an unchecked checkbox submits no key and — because the save loop
overlays submitted keys onto the loaded raw config (`settings.py:46-56`) —
would leave a `true` boolean stuck on. `_coerce` gains a boolean branch so known
`*_enabled` keys persist as real YAML bools.

## 5. Reports

### 5.1 Architecture

New aggregation methods on `EventRepo` (pure SQL over the existing `events`
table — **no schema change**), a server-rendered `/reports` page, and a
`/api/reports` partial for the htmx window switch. Both behind
`require_session`. SQLite `strftime` does the hour-of-day and per-day
grouping.

### 5.2 Time window

A selector — **Today / 7d / 30d / All** — passed as a query param and mapped to
a UTC `start` cutoff. Default `7d`. The htmx switch swaps the dashboard
partial.

### 5.3 Dashboard contents

1. **Summary stats** — count, median, p85, max (the headline numbers).
2. **Speed histogram** — counts per speed bucket, bucketed in user display
   units (e.g. 5 mph / 5 kph bins).
3. **By hour-of-day** — vehicle counts per hour 0–23.
4. **Daily-volume trend** — count per day across the window.
5. **Per-direction breakdown** — L2R vs R2L counts + medians.
6. **Busiest-hour callout** — derived from (3).

### 5.4 Charts

**Server-rendered inline SVG in Jinja** — bars are `<rect>`, the trend is a
`<polyline>`. Zero new frontend dependencies; holds the no-build-step ethos.
The repo returns plain aggregate rows; the template computes bar geometry.

### 5.5 Honest precision

Speeds are bucketed/rounded (5-unit bins; summary stats to whole units) so the
dashboard never implies more precision than the two-scale calibration
delivers.

### 5.6 UI

A new top-nav link → `/reports`, laid out with the existing design-system
tokens (cards + the chart SVGs). Empty-state copy when the window has no
events.

## 6. Dependencies

- **`paho-mqtt`** — new runtime dependency, added to the **base** image deps in
  `pyproject.toml` (not the picamera-only extra). Required for the MQTT
  channel.
- `httpx` — already a dependency (ntfy + webhook).

## 7. Testing

- **Unit — dispatcher:** qualifying rule; per-channel cooldown (incl. `0`
  disables); per-channel failure isolation; ntfy/webhook/MQTT payload shape.
  Fake httpx + MQTT clients — no network.
- **Unit — config:** `AlertsSettings` YAML round-trip; `CURBCAM_ALERTS__*` env
  override shadows a field read-only in the form.
- **Unit — reports repo:** seeded event set with a known histogram / hour
  distribution / percentiles; assert aggregate rows.
- **Integration — web:** `/reports` and `/api/reports` against the
  FileReplay-backed app; window filtering changes the numbers; nav link
  present; empty-state renders.
- Existing CSV/events/settings tests must stay green.

## 8. Risks

- **MQTT broker connectivity** is environmental — handled by fire-and-forget
  publish with lazy connect/reconnect and per-channel failure isolation, so a
  down broker degrades to a logged warning, never a stalled loop.
- **Cooldown is in-memory**, so a restart re-arms every channel; acceptable for
  a single-process homelab tool.
- **Click-through link correctness** depends on `base_url` matching the user's
  actual access URL; the mDNS default is the documented install path, and the
  field is user-editable.

## 9. Out of scope / future (recap)

Quiet hours; HA MQTT discovery / per-event sensors; channel-specific
formatters; alert delivery history; image attachments; email/SMS. All future.
