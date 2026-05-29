# curbcam

A modern, neighbor-friendly speed camera for Raspberry Pi.

Detects moving vehicles, calculates speed, stores results — all configurable
through a web UI with a guided calibration wizard. No SSH required for normal
use.

**Status:** MVP-2 (web app: dashboard, live preview, wizards) — see
[`docs/specs/2026-05-28-curbcam-mvp-2-web.md`](docs/specs/2026-05-28-curbcam-mvp-2-web.md).

## What works today (MVP-1)

A command-line speed-camera pipeline:

```bash
# 1. Install (dev environment — Pi-friendly Docker image is MVP-3)
git clone https://github.com/PatientVibes/curbcam
cd curbcam
uv venv && uv pip install -e ".[dev]"

# 2. Seed a calibration (one-time; MVP-2 replaces this with a web wizard)
uv run curbcam calibrate \
    --mm-per-px-l2r 41.3 --mm-per-px-r2l 41.5 \
    --reference-distance-mm 4700

# 3. Run the detector against a camera or a directory of frames
uv run curbcam detect --camera usb:0
# or
uv run curbcam detect --camera rtsp://user:pw@cam.local/stream
# or (dev / debugging)
uv run curbcam detect --camera file:./fixtures/sample_run --once
```

Events land in `./data/curbcam.sqlite`; thumbnails and full-frame JPEGs in
`./media/`.

## Run the web app (MVP-2)

```bash
uv run curbcam serve            # http://<pi-ip>:8000
```

On first launch every page redirects to a setup wizard:

1. Set a single admin password.
2. Acknowledge the privacy notice (check your local laws — §15).
3. Pick a camera source and confirm the live preview.
4. **Align** — drag a rectangle over the road to set the detection region.
5. **Calibrate** — capture a frame, click the two ends of a known-length
   object, enter the real-world distance and travel direction.

After setup: a dashboard with live MJPEG + an event feed, a filterable Events
history with CSV export, and Settings (saving restarts the detector). Embed the
preview elsewhere (e.g. Home Assistant) with a revocable stream token from
**Settings → Integrations**: `http://<pi-ip>:8000/api/stream.mjpeg?token=...`.

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
setup, and a single Docker-based deployment path (MVP-3).

## License

MIT.
