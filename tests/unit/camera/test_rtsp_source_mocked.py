"""RtspSource unit tests using mocked cv2 — no hardware required."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from curbcam.camera.rtsp_source import RtspSource


def _make_source(**kw) -> RtspSource:
    defaults = dict(resolution=(640, 480), fps_target=15.0)
    defaults.update(kw)
    return RtspSource("rtsp://test-host/stream", **defaults)


# ---------------------------------------------------------------------------
# open() — success on first attempt
# ---------------------------------------------------------------------------


def test_rtsp_open_success_first_attempt() -> None:
    src = _make_source()
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True

    with patch("curbcam.camera.rtsp_source.cv2.VideoCapture", return_value=mock_cap):
        src.open()

    assert src._cap is mock_cap


def test_rtsp_open_idempotent() -> None:
    """Calling open() a second time when already open is a no-op."""
    src = _make_source()
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True

    with patch("curbcam.camera.rtsp_source.cv2.VideoCapture", return_value=mock_cap) as ctor:
        src.open()
        src.open()  # second call — should not open again

    assert ctor.call_count == 1


# ---------------------------------------------------------------------------
# open() — exhausts retries and raises
# ---------------------------------------------------------------------------


def test_rtsp_open_exhausts_retries_and_raises() -> None:
    src = _make_source(max_open_attempts=3)
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = False  # always fails

    with (
        patch("curbcam.camera.rtsp_source.cv2.VideoCapture", return_value=mock_cap),
        patch("curbcam.camera.rtsp_source.time.sleep"),  # skip backoff waits
        pytest.raises(RuntimeError, match="Could not open RTSP"),
    ):
        src.open()

    # All 3 attempts released their cap
    assert mock_cap.release.call_count == 3


# ---------------------------------------------------------------------------
# read() — happy path and transient failure (triggers reconnect)
# ---------------------------------------------------------------------------


def test_rtsp_read_returns_frame_on_success() -> None:
    src = _make_source()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (True, frame)

    with patch("curbcam.camera.rtsp_source.cv2.VideoCapture", return_value=mock_cap):
        src.open()
        result = src.read()

    assert result is not None
    got_frame, ts = result
    assert got_frame is frame
    assert ts > 0.0


def test_rtsp_read_none_on_failure_and_closes_cap() -> None:
    """When cap.read() fails, read() returns None and resets _cap (reconnect)."""
    src = _make_source()
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (False, None)

    with patch("curbcam.camera.rtsp_source.cv2.VideoCapture", return_value=mock_cap):
        src.open()
        result = src.read()

    assert result is None
    # close() should have been called, resetting _cap
    assert src._cap is None
    mock_cap.release.assert_called_once()


# ---------------------------------------------------------------------------
# close()
# ---------------------------------------------------------------------------


def test_rtsp_close_releases_cap() -> None:
    src = _make_source()
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True

    with patch("curbcam.camera.rtsp_source.cv2.VideoCapture", return_value=mock_cap):
        src.open()

    src.close()
    mock_cap.release.assert_called_once()
    assert src._cap is None


def test_rtsp_close_when_not_open_is_safe() -> None:
    src = _make_source()
    src.close()  # must not raise


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


def test_rtsp_resolution_property() -> None:
    src = _make_source(resolution=(1280, 720))
    assert src.resolution == (1280, 720)


def test_rtsp_fps_target_property() -> None:
    src = _make_source(fps_target=30.0)
    assert src.fps_target == 30.0


def test_rtsp_is_persistent() -> None:
    src = _make_source()
    assert src.is_persistent is True
