"""Best-effort discovery of locally attached cameras for the setup wizard.

Enumeration is intentionally lightweight and side-effect free: we never
start a capture pipeline, only query metadata (picamera2's global camera
info and V4L2 ``QUERYCAP`` ioctls). Every backend probe is wrapped so a
failure in one — or a missing dependency, or a non-Linux dev machine —
never breaks the others. The worst case is an empty list, and the setup
wizard always offers manual entry (needed anyway for RTSP/file sources).
"""

from __future__ import annotations

import glob
import logging
import os
import struct
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiscoveredCamera:
    source: str  # ready-to-use camera_from_source() string, e.g. "picamera2:0"
    label: str  # human-friendly description for the dropdown
    kind: str  # "picamera2" | "usb"


def discover_cameras() -> list[DiscoveredCamera]:
    """Enumerate attached cameras. Best-effort; never raises."""
    cameras: list[DiscoveredCamera] = []
    for probe in (_discover_picamera2, _discover_v4l2):
        try:
            cameras.extend(probe())
        except Exception:
            # Discovery is strictly best-effort — a failing probe must not
            # break the others or the setup page. Surface it only in debug.
            logger.debug("camera discovery probe %s failed", probe.__name__, exc_info=True)
    return cameras


def _discover_picamera2() -> list[DiscoveredCamera]:
    try:
        from picamera2 import Picamera2  # type: ignore[import-not-found]
    except ImportError:
        return []
    out: list[DiscoveredCamera] = []
    for idx, info in enumerate(Picamera2.global_camera_info()):
        num = info.get("Num", idx)
        model = info.get("Model") or "Pi Camera"
        out.append(
            DiscoveredCamera(
                source=f"picamera2:{num}",
                label=f"Pi Camera {num} — {model}",
                kind="picamera2",
            )
        )
    return out


# --- V4L2 capability probe (Linux) -----------------------------------------
#
# We query each /dev/video* node's capabilities via the VIDIOC_QUERYCAP
# ioctl rather than opening a cv2.VideoCapture stream — querying is fast and
# can't conflict with a camera that's already in use.
#
# A Pi exposes ~15 /dev/video* nodes: the real CSI sensor plus many internal
# unicam/ISP/codec nodes, several of which falsely advertise VIDEO_CAPTURE.
# We therefore restrict V4L2 discovery to genuine USB webcams (uvcvideo
# driver or a usb-* bus) and drop mem2mem nodes (which also expose
# VIDEO_OUTPUT). The CSI camera is offered separately via picamera2, so it is
# intentionally not surfaced here as a raw V4L2 node. Struct layout and ioctl
# number are from <linux/videodev2.h>.

_V4L2_CAP_VIDEO_CAPTURE = 0x00000001
_V4L2_CAP_VIDEO_OUTPUT = 0x00000002
_V4L2_CAP_DEVICE_CAPS = 0x80000000
# struct v4l2_capability: driver[16], card[32], bus_info[32],
# version u32, capabilities u32, device_caps u32, reserved[3] u32 = 104 bytes
_QUERYCAP_FMT = "16s32s32sIII3I"
_QUERYCAP_SIZE = struct.calcsize(_QUERYCAP_FMT)
# VIDIOC_QUERYCAP = _IOR('V', 0, struct v4l2_capability)
_IOC_READ = 2
_VIDIOC_QUERYCAP = (_IOC_READ << 30) | (_QUERYCAP_SIZE << 16) | (ord("V") << 8) | 0


@dataclass(frozen=True)
class _V4l2Cap:
    driver: str
    card: str
    bus_info: str
    is_capture: bool
    is_output: bool


def _v4l2_querycap(path: str) -> _V4l2Cap | None:
    """Query a V4L2 node's capabilities, or None if it can't be queried."""
    # fcntl is Linux-only; import lazily so this module (and everything that
    # imports it, e.g. the web routes) still loads on Windows/macOS dev
    # machines. discover_cameras() catches the ImportError as an empty probe.
    import fcntl

    try:
        fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        buf = bytearray(_QUERYCAP_SIZE)
        fcntl.ioctl(fd, _VIDIOC_QUERYCAP, buf)
    except OSError:
        return None
    finally:
        os.close(fd)
    driver, card, bus, _version, caps, device_caps = struct.unpack(_QUERYCAP_FMT, bytes(buf))[:6]
    effective = device_caps if (caps & _V4L2_CAP_DEVICE_CAPS) else caps
    return _V4l2Cap(
        driver=_cstr(driver),
        card=_cstr(card),
        bus_info=_cstr(bus),
        is_capture=bool(effective & _V4L2_CAP_VIDEO_CAPTURE),
        is_output=bool(effective & _V4L2_CAP_VIDEO_OUTPUT),
    )


def _cstr(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("ascii", "replace").strip()


def _is_usb_camera(cap: _V4l2Cap) -> bool:
    # A real, selectable capture device: captures, isn't a mem2mem node, and
    # sits on USB (uvcvideo driver or a usb-* bus). This excludes the Pi's
    # internal unicam/bcm2835-isp/codec nodes.
    if not cap.is_capture or cap.is_output:
        return False
    return cap.driver == "uvcvideo" or cap.bus_info.startswith("usb")


def _video_index(path: str) -> int:
    try:
        return int(path.rsplit("video", 1)[1])
    except (IndexError, ValueError):
        return 0


def _discover_v4l2() -> list[DiscoveredCamera]:
    out: list[DiscoveredCamera] = []
    for path in sorted(glob.glob("/dev/video*"), key=_video_index):
        cap = _v4l2_querycap(path)
        if cap is None or not _is_usb_camera(cap):
            continue
        out.append(
            DiscoveredCamera(
                source=f"usb:{path}",
                label=f"{cap.card or 'USB camera'} ({path})",
                kind="usb",
            )
        )
    return out
