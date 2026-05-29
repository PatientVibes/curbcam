"""MDNSPublisher builds the right ServiceInfo and registers/unregisters it.
A fake Zeroconf is injected so no multicast happens in the test."""

from __future__ import annotations

import socket

from curbcam.discovery.mdns import MDNSPublisher


class _FakeZeroconf:
    def __init__(self) -> None:
        self.registered: list = []
        self.unregistered: list = []
        self.closed = False

    def register_service(self, info) -> None:  # type: ignore[no-untyped-def]
        self.registered.append(info)

    def unregister_service(self, info) -> None:  # type: ignore[no-untyped-def]
        self.unregistered.append(info)

    def close(self) -> None:
        self.closed = True


def test_start_registers_expected_service() -> None:
    zc = _FakeZeroconf()
    pub = MDNSPublisher("192.168.1.50", 8080, zeroconf=zc)
    pub.start()

    assert len(zc.registered) == 1
    info = zc.registered[0]
    assert info.type == "_http._tcp.local."
    assert info.name == "curbcam._http._tcp.local."
    assert info.server == "curbcam.local."
    assert info.port == 8080
    assert socket.inet_ntoa(info.addresses[0]) == "192.168.1.50"


def test_stop_unregisters_and_closes() -> None:
    zc = _FakeZeroconf()
    pub = MDNSPublisher("10.0.0.5", 8080, zeroconf=zc)
    pub.start()
    info = zc.registered[0]
    pub.stop()

    assert zc.unregistered == [info]
    assert zc.closed is True


def test_stop_is_safe_before_start() -> None:
    zc = _FakeZeroconf()
    pub = MDNSPublisher("10.0.0.5", 8080, zeroconf=zc)
    pub.stop()  # must not raise
    assert zc.unregistered == []
