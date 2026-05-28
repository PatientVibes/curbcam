# curbcam

A modern, neighbor-friendly speed camera for Raspberry Pi.

Detects moving vehicles, calculates speed, stores results — all configurable
through a web UI (coming in MVP-2) with a guided calibration wizard. No SSH
required for normal use.

**Status:** MVP-1 (headless detector + CLI) — see
[`docs/specs/2026-05-28-curbcam-design.md`](docs/specs/2026-05-28-curbcam-design.md)
for the full design.

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
