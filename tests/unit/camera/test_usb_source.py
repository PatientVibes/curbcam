"""USB source tests — skipped unless a real device is available.

Set CURBCAM_TEST_USB_DEVICE=/dev/video0 (or an integer) to enable.
"""
import os

import pytest

from curbcam.camera.usb_source import UsbSource

_DEVICE = os.environ.get("CURBCAM_TEST_USB_DEVICE")


@pytest.mark.skipif(_DEVICE is None, reason="set CURBCAM_TEST_USB_DEVICE to run")
def test_usb_source_reads_a_frame() -> None:
    device: str | int = int(_DEVICE) if _DEVICE.isdigit() else _DEVICE   # type: ignore[arg-type, union-attr]
    cam = UsbSource(device, resolution=(640, 480), fps_target=15.0)
    cam.open()
    try:
        got = cam.read()
        assert got is not None
        frame, _ts = got
        assert frame.shape[2] == 3
    finally:
        cam.close()


def test_usb_source_read_before_open_raises() -> None:
    cam = UsbSource(0, resolution=(640, 480), fps_target=15.0)
    with pytest.raises(RuntimeError):
        cam.read()
