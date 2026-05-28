"""RTSP source tests — skipped unless a real URL is available.

Set CURBCAM_TEST_RTSP_URL=rtsp://... to enable.
"""

import os

import pytest

from curbcam.camera.rtsp_source import RtspSource

_URL = os.environ.get("CURBCAM_TEST_RTSP_URL")


@pytest.mark.skipif(_URL is None, reason="set CURBCAM_TEST_RTSP_URL to run")
def test_rtsp_source_reads_a_frame() -> None:
    cam = RtspSource(_URL or "", resolution=(640, 480), fps_target=15.0)
    cam.open()
    try:
        got = cam.read()
        assert got is not None
    finally:
        cam.close()


def test_rtsp_source_read_before_open_raises() -> None:
    cam = RtspSource("rtsp://noop", resolution=(640, 480), fps_target=15.0)
    with pytest.raises(RuntimeError):
        cam.read()
