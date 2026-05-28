"""Picamera2Source unit tests — picamera2 library is mocked throughout."""

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from curbcam.camera.picamera2_source import Picamera2Source


def _make_source(**kw) -> Picamera2Source:
    defaults = dict(resolution=(640, 480), fps_target=30.0)
    defaults.update(kw)
    return Picamera2Source(0, **defaults)


def _mock_picamera2_module() -> tuple[ModuleType, MagicMock]:
    """Return a fake picamera2 module and the Picamera2 class mock inside it."""
    fake_mod = ModuleType("picamera2")
    cam_cls = MagicMock()
    fake_mod.Picamera2 = cam_cls  # type: ignore[attr-defined]
    return fake_mod, cam_cls


# ---------------------------------------------------------------------------
# open() — success path
# ---------------------------------------------------------------------------


def test_picamera2_open_success() -> None:
    src = _make_source()
    fake_mod, cam_cls = _mock_picamera2_module()
    cam_instance = cam_cls.return_value

    with patch.dict(sys.modules, {"picamera2": fake_mod}):
        src.open()

    cam_cls.assert_called_once_with(camera_num=0)
    cam_instance.configure.assert_called_once()
    cam_instance.start.assert_called_once()
    assert src._cam is cam_instance


def test_picamera2_open_idempotent() -> None:
    src = _make_source()
    fake_mod, cam_cls = _mock_picamera2_module()

    with patch.dict(sys.modules, {"picamera2": fake_mod}):
        src.open()
        src.open()  # second call — should not re-open

    assert cam_cls.call_count == 1


def test_picamera2_open_raises_when_import_fails() -> None:
    src = _make_source()
    # Ensure picamera2 is NOT importable
    with patch.dict(sys.modules, {"picamera2": None}):  # type: ignore[dict-item]
        with pytest.raises(RuntimeError, match="picamera2 is not installed"):
            src.open()


# ---------------------------------------------------------------------------
# read()
# ---------------------------------------------------------------------------


def test_picamera2_read_before_open_raises() -> None:
    src = _make_source()
    with pytest.raises(RuntimeError, match="read\\(\\) before open\\(\\)"):
        src.read()


def test_picamera2_read_returns_frame() -> None:
    src = _make_source()
    fake_mod, cam_cls = _mock_picamera2_module()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cam_instance = cam_cls.return_value
    cam_instance.capture_array.return_value = frame

    with patch.dict(sys.modules, {"picamera2": fake_mod}):
        src.open()
        result = src.read()

    assert result is not None
    got_frame, ts = result
    assert got_frame is frame
    assert ts > 0.0


def test_picamera2_read_returns_none_when_capture_returns_none() -> None:
    src = _make_source()
    fake_mod, cam_cls = _mock_picamera2_module()
    cam_instance = cam_cls.return_value
    cam_instance.capture_array.return_value = None

    with patch.dict(sys.modules, {"picamera2": fake_mod}):
        src.open()
        result = src.read()

    assert result is None


# ---------------------------------------------------------------------------
# close()
# ---------------------------------------------------------------------------


def test_picamera2_close_stops_and_closes_cam() -> None:
    src = _make_source()
    fake_mod, cam_cls = _mock_picamera2_module()
    cam_instance = cam_cls.return_value

    with patch.dict(sys.modules, {"picamera2": fake_mod}):
        src.open()

    src.close()
    cam_instance.stop.assert_called_once()
    cam_instance.close.assert_called_once()
    assert src._cam is None


def test_picamera2_close_when_not_open_is_safe() -> None:
    src = _make_source()
    src.close()  # must not raise


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


def test_picamera2_resolution_property() -> None:
    src = _make_source(resolution=(1280, 720))
    assert src.resolution == (1280, 720)


def test_picamera2_fps_target_property() -> None:
    src = _make_source(fps_target=60.0)
    assert src.fps_target == 60.0


def test_picamera2_is_persistent() -> None:
    src = _make_source()
    assert src.is_persistent is True
