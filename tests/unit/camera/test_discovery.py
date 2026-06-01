"""Unit tests for best-effort camera discovery."""

from __future__ import annotations

import sys
import types

from curbcam.camera import discovery
from curbcam.camera.discovery import DiscoveredCamera, _V4l2Cap


def _cap(*, driver="uvcvideo", card="USB Cam", bus="usb-0000:01.0", capture=True, output=False):  # type: ignore[no-untyped-def]
    return _V4l2Cap(driver=driver, card=card, bus_info=bus, is_capture=capture, is_output=output)


def test_discover_v4l2_lists_only_usb_capture_nodes(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(discovery.glob, "glob", lambda _pat: ["/dev/video1", "/dev/video0"])
    caps = {
        "/dev/video0": _cap(card="USB Cam"),  # real USB webcam -> kept
        "/dev/video1": _cap(capture=False),  # not a capture node -> skipped
    }
    monkeypatch.setattr(discovery, "_v4l2_querycap", lambda path: caps.get(path))

    out = discovery._discover_v4l2()

    assert [c.source for c in out] == ["usb:/dev/video0"]  # sorted by index, capture-only
    assert out[0].kind == "usb"
    assert "USB Cam" in out[0].label


def test_discover_v4l2_excludes_pi_internal_and_m2m_nodes(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # The Pi's unicam/ISP nodes advertise capture but live on a platform bus,
    # and the ISP/codec mem2mem nodes also advertise VIDEO_OUTPUT.
    monkeypatch.setattr(discovery.glob, "glob", lambda _pat: ["/dev/video0", "/dev/video14"])
    caps = {
        "/dev/video0": _cap(driver="unicam", card="unicam", bus="platform:..."),
        "/dev/video14": _cap(
            driver="bcm2835-isp", card="bcm2835-isp", bus="platform:...", output=True
        ),
    }
    monkeypatch.setattr(discovery, "_v4l2_querycap", lambda path: caps.get(path))
    assert discovery._discover_v4l2() == []


def test_discover_v4l2_skips_unqueryable_nodes(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(discovery.glob, "glob", lambda _pat: ["/dev/video0"])
    monkeypatch.setattr(discovery, "_v4l2_querycap", lambda _path: None)
    assert discovery._discover_v4l2() == []


def test_discover_picamera2_uses_global_camera_info(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fake = types.ModuleType("picamera2")

    class FakePicamera2:
        @staticmethod
        def global_camera_info() -> list[dict[str, object]]:
            return [{"Model": "imx708", "Num": 0}]

    fake.Picamera2 = FakePicamera2  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "picamera2", fake)

    out = discovery._discover_picamera2()

    assert out[0].source == "picamera2:0"
    assert out[0].kind == "picamera2"
    assert "imx708" in out[0].label


def test_discover_picamera2_absent_returns_empty(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setitem(sys.modules, "picamera2", None)  # import raises -> []
    assert discovery._discover_picamera2() == []


def test_discover_cameras_swallows_probe_errors(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def boom() -> list[DiscoveredCamera]:
        raise RuntimeError("probe blew up")

    monkeypatch.setattr(discovery, "_discover_picamera2", boom)
    monkeypatch.setattr(
        discovery, "_discover_v4l2", lambda: [DiscoveredCamera("usb:/dev/video0", "Cam", "usb")]
    )

    out = discovery.discover_cameras()

    assert [c.source for c in out] == ["usb:/dev/video0"]  # surviving probe still contributes
