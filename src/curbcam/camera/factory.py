"""Map a config string to a Camera implementation.

Format examples:
    picamera2:0
    picamera2:1
    usb:0                      (integer device index)
    usb:/dev/video0            (string device path)
    rtsp://user:pw@host:554/s
    file:./fixtures/sample
"""
from pathlib import Path

from curbcam.camera.base import Camera
from curbcam.camera.file_replay import FileReplaySource
from curbcam.camera.picamera2_source import Picamera2Source
from curbcam.camera.rtsp_source import RtspSource
from curbcam.camera.usb_source import UsbSource


def camera_from_source(
    source: str,
    *,
    resolution: tuple[int, int],
    fps_target: float,
) -> Camera:
    if source.startswith("picamera2:"):
        idx = int(source.split(":", 1)[1])
        return Picamera2Source(idx, resolution=resolution, fps_target=fps_target)
    if source.startswith("usb:"):
        rest = source.split(":", 1)[1]
        device: str | int = int(rest) if rest.isdigit() else rest
        return UsbSource(device, resolution=resolution, fps_target=fps_target)
    if source.startswith("rtsp://") or source.startswith("rtsps://"):
        return RtspSource(source, resolution=resolution, fps_target=fps_target)
    if source.startswith("file:"):
        path = Path(source.split(":", 1)[1])
        return FileReplaySource(path, fps_target=fps_target, loop=True)
    raise ValueError(f"Unknown camera source: {source!r}")
