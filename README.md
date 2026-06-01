# curbcam

A modern, neighbor-friendly speed camera for Raspberry Pi.

Detects moving vehicles, calculates speed, stores results — all configurable
through a web UI with a guided calibration wizard. No SSH required for normal
use.

**Status:** MVP-3 (Docker install + mDNS discovery) — see [`docs/specs/2026-05-29-curbcam-mvp-3-docker-install.md`](docs/specs/2026-05-29-curbcam-mvp-3-docker-install.md).

## Install (Docker)

```bash
mkdir curbcam && cd curbcam
curl -O https://raw.githubusercontent.com/PatientVibes/curbcam/main/docker-compose.yml
docker compose up -d
# then browse to http://curbcam.local:8080
```

Three commands. The image is multi-arch (Raspberry Pi arm64 + x86 amd64) and
published to GHCR. On first launch every page redirects to the setup wizard
(password → privacy notice → camera → align → calibrate).

**Updating:** `docker compose pull && docker compose up -d`. The container runs
database migrations automatically on boot, so upgrades are safe.

**Cameras in Docker:** USB (`usb:0`), RTSP (`rtsp://…`), and file replay run on
the standard multi-arch image. The **Raspberry Pi Camera Module** runs on a
dedicated arm64 image — see below. Keep RTSP credentials in a gitignored `.env`
(see `.env.example`) rather than in `curbcam.yaml`.

### Raspberry Pi Camera Module

The Pi Camera Module (libcamera/picamera2) runs on a dedicated **arm64-only**
image, `ghcr.io/patientvibes/curbcam:picamera`, with its own compose file:

```bash
mkdir curbcam && cd curbcam
curl -O https://raw.githubusercontent.com/PatientVibes/curbcam/main/docker-compose.picamera.yml
docker compose -f docker-compose.picamera.yml up -d
# browse to http://curbcam.local:8080
```

This image bases on Debian Trixie and installs libcamera + picamera2 from the
Raspberry Pi apt archive. It runs `privileged: true` by default — the reliable
path for camera-device access on a dedicated Pi; advanced users can switch to the
scoped device list commented in the compose file. Requires 64-bit Raspberry Pi OS
and `docker compose` (v2 — included with Docker CE; Debian's `docker.io` ships
only Compose v1, so install the plugin there).

## Develop from source

```bash
git clone https://github.com/PatientVibes/curbcam
cd curbcam
uv venv && uv pip install -e ".[dev]"

uv run curbcam serve            # http://localhost:8000  (mDNS on; --no-mdns to disable)
```

For detector-only work without the web UI:

```bash
# Seed a calibration (one-time; the web wizard is the normal path)
uv run curbcam calibrate \
    --mm-per-px-l2r 41.3 --mm-per-px-r2l 41.5 \
    --reference-distance-mm 4700

# Run the detector against a camera or a directory of frames
uv run curbcam detect --camera usb:0
uv run curbcam detect --camera rtsp://user:pw@cam.local/stream
uv run curbcam detect --camera file:./fixtures/sample_run --once
```

Events land in `./data/curbcam.sqlite`; thumbnails and full-frame JPEGs in
`./media/`.

On first launch the web UI redirects to a setup wizard:

1. Set a single admin password.
2. Acknowledge the privacy notice (check your local laws — §15).
3. Pick a camera source and confirm the live preview.
4. **Align** — drag a rectangle over the road to set the detection region.
5. **Calibrate** — capture a frame, click the two ends of a known-length
   object, enter the real-world distance and travel direction.

After setup: a dashboard with live MJPEG + an event feed, a filterable Events
history with CSV export, a **Reports** dashboard, and Settings (saving restarts
the detector). Embed the preview elsewhere (e.g. Home Assistant) with a
revocable stream token from **Settings → Integrations**:
`http://<pi-ip>:8000/api/stream.mjpeg?token=...`.

### Reports

The **Reports** page (linked from the nav, next to Events) summarises traffic
over a selectable window — Today, 7 days, 30 days, or All. It shows vehicle
count, median / 85th-percentile / max speed (in your display units), plus
inline-SVG charts for the speed distribution, traffic by hour of day, the daily
volume trend, and a per-direction breakdown. No frontend build step — the charts
are server-rendered SVG.

### Alerts

curbcam can push a notification whenever a vehicle is detected at or above a
speed you choose. Configure everything under **Settings → Alerts**:

- **Master switch + threshold.** Alerts are off by default. Set an *Alert speed*
  (independent of the recording threshold — usually set it higher) so only the
  vehicles you care about fire a notification.
- **Channels.** Three independent transports, each separately toggleable:
  - **ntfy** — push to your phone via an [ntfy](https://ntfy.sh) topic
    (default server `https://ntfy.sh`; the alert links back to your Events page).
  - **Webhook** — POST a JSON body (event id, speed in km/h and display units,
    direction, timestamp, link) to any URL.
  - **MQTT** — publish the same JSON to an MQTT broker (e.g. for Home Assistant).
    **Requires a broker** — set the host, port (default `1883`), topic, and
    optional username/password.
- **Per-channel cooldown.** Each channel has a *cooldown (seconds)* to throttle
  notifications. `0` fires on every qualifying event (the right setting for
  MQTT → Home Assistant); the HTTP channels default to `60`.

No extra install step for alerts — `paho-mqtt` (the MQTT client) ships in the
Docker image and in the `[dev]` extra.

### Mounting for best accuracy

Speed accuracy is limited by perspective and centroid jitter, not pixel count.
Two tips that beat any software setting:

- **Angle the camera somewhat down the road**, not straight across — this
  flattens the near/far depth gradient and reduces perspective error.
- **Calibrate each direction** against a reference at that lane's distance; the
  two-scale model (`mm_per_px_l2r` / `mm_per_px_r2l`) exists for exactly the
  near-lane/far-lane depth difference.

(A perspective-homography calibration is planned for a future "calibration v2";
it is the lever that would tighten accuracy further.)

## Camera sources

| Prefix | Example | Notes |
|---|---|---|
| `picamera2:` | `picamera2:0` | Raspberry Pi Camera Module via libcamera. Requires `uv pip install '.[picamera2]'` on the Pi. |
| `usb:` | `usb:0` or `usb:/dev/video0` | Any V4L2 / DirectShow webcam OpenCV can open. |
| `rtsp://` | `rtsp://user:pw@host/stream` | IP cameras. Stores credentials in plaintext — prefer the env-var override (see below). |
| `file:` | `file:./fixtures/sample_run` | Replays a directory of JPEGs. Dev + tests. |

### Avoiding plaintext RTSP credentials

```bash
export CURBCAM_CAMERA__SOURCE="rtsp://user:pw@host/stream"
uv run curbcam detect       # no credentials in the YAML config
```

## Before you install

Speed cameras inherently capture people, vehicles, and license plates in
public or semi-public spaces. The legal status of doing so varies by
jurisdiction (GDPR in the EU, state-by-state in the US, etc.). **Check
your local laws before pointing this at a public road or shared space.**
This project's defaults are private-network-only — nothing is exposed
externally, no data leaves your device, no license-plate OCR is shipped.
See the design spec's *Responsible Use & Privacy* section (§15) for the
project's full stance.

## Inspiration

Inspired by [pageauc/speed-camera](https://github.com/pageauc/speed-camera),
re-implemented from scratch with a focus on installability, wizard-driven
setup, and a single Docker-based deployment path.

## License

MIT.
