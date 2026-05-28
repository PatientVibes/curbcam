from pathlib import Path

import pytest

from curbcam.camera.factory import camera_from_source
from curbcam.camera.file_replay import FileReplaySource


def test_factory_returns_file_replay_for_file_source(tmp_path: Path) -> None:
    # Create a single dummy frame so FileReplaySource.open() can probe shape.
    import cv2
    import numpy as np

    cv2.imwrite(str(tmp_path / "0001.jpg"), np.zeros((10, 10, 3), dtype=np.uint8))

    cam = camera_from_source(f"file:{tmp_path}", resolution=(640, 480), fps_target=10.0)
    assert isinstance(cam, FileReplaySource)


def test_factory_routes_usb_prefix() -> None:
    from curbcam.camera.usb_source import UsbSource

    cam = camera_from_source("usb:0", resolution=(640, 480), fps_target=15.0)
    assert isinstance(cam, UsbSource)


def test_factory_routes_rtsp_prefix() -> None:
    from curbcam.camera.rtsp_source import RtspSource

    cam = camera_from_source(
        "rtsp://example.invalid/stream", resolution=(640, 480), fps_target=15.0
    )
    assert isinstance(cam, RtspSource)


def test_factory_routes_picamera2_prefix() -> None:
    from curbcam.camera.picamera2_source import Picamera2Source

    cam = camera_from_source("picamera2:0", resolution=(640, 480), fps_target=15.0)
    assert isinstance(cam, Picamera2Source)


def test_factory_raises_on_unknown_prefix() -> None:
    with pytest.raises(ValueError, match="Unknown camera source"):
        camera_from_source("magic:thing", resolution=(640, 480), fps_target=15.0)
