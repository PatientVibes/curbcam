"""UsbSource unit tests using mocked cv2 — no hardware required."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from curbcam.camera.usb_source import UsbSource


def _make_source(**kw) -> UsbSource:
    defaults = dict(resolution=(640, 480), fps_target=30.0)
    defaults.update(kw)
    return UsbSource(0, **defaults)


# ---------------------------------------------------------------------------
# open()
# ---------------------------------------------------------------------------


def test_usb_open_success() -> None:
    src = _make_source()
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True

    with patch("curbcam.camera.usb_source.cv2.VideoCapture", return_value=mock_cap):
        src.open()

    assert src._cap is mock_cap
    # Resolution and FPS should have been set
    mock_cap.set.assert_called()


def test_usb_open_idempotent() -> None:
    src = _make_source()
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True

    with patch("curbcam.camera.usb_source.cv2.VideoCapture", return_value=mock_cap) as ctor:
        src.open()
        src.open()  # second call should be a no-op

    assert ctor.call_count == 1


def test_usb_open_raises_when_device_unavailable() -> None:
    src = _make_source()
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = False

    with (
        patch("curbcam.camera.usb_source.cv2.VideoCapture", return_value=mock_cap),
        pytest.raises(RuntimeError, match="Could not open USB camera"),
    ):
        src.open()


# ---------------------------------------------------------------------------
# read()
# ---------------------------------------------------------------------------


def test_usb_read_returns_frame_on_success() -> None:
    src = _make_source()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (True, frame)

    with patch("curbcam.camera.usb_source.cv2.VideoCapture", return_value=mock_cap):
        src.open()
        result = src.read()

    assert result is not None
    got_frame, ts = result
    assert got_frame is frame
    assert ts > 0.0


def test_usb_read_returns_none_on_transient_failure() -> None:
    src = _make_source()
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (False, None)

    with patch("curbcam.camera.usb_source.cv2.VideoCapture", return_value=mock_cap):
        src.open()
        result = src.read()

    assert result is None


# ---------------------------------------------------------------------------
# close()
# ---------------------------------------------------------------------------


def test_usb_close_releases_cap() -> None:
    src = _make_source()
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True

    with patch("curbcam.camera.usb_source.cv2.VideoCapture", return_value=mock_cap):
        src.open()

    src.close()
    mock_cap.release.assert_called_once()
    assert src._cap is None


def test_usb_close_when_not_open_is_safe() -> None:
    src = _make_source()
    src.close()  # must not raise


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


def test_usb_resolution_property() -> None:
    src = _make_source(resolution=(1920, 1080))
    assert src.resolution == (1920, 1080)


def test_usb_fps_target_property() -> None:
    src = _make_source(fps_target=60.0)
    assert src.fps_target == 60.0


def test_usb_is_persistent() -> None:
    src = _make_source()
    assert src.is_persistent is True
