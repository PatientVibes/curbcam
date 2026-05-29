"""detect_lan_ip uses a UDP socket's chosen source address (no packet sent)
and falls back to loopback on any OSError. Both paths are tested without
real networking by substituting a fake socket."""
from __future__ import annotations

import socket

import curbcam.discovery.net as net


class _FakeSocket:
    def __init__(self, *_a, **_k) -> None:
        self.closed = False

    def connect(self, _addr) -> None:
        pass

    def getsockname(self) -> tuple[str, int]:
        return ("192.168.1.42", 12345)

    def close(self) -> None:
        self.closed = True


class _RaisingSocket(_FakeSocket):
    def connect(self, _addr) -> None:
        raise OSError("network unreachable")


def test_detect_lan_ip_returns_source_address(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(net.socket, "socket", _FakeSocket)
    assert net.detect_lan_ip() == "192.168.1.42"


def test_detect_lan_ip_falls_back_to_loopback(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(net.socket, "socket", _RaisingSocket)
    assert net.detect_lan_ip() == "127.0.0.1"


def test_detect_lan_ip_closes_the_socket(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    created: list[_FakeSocket] = []

    def _factory(*a, **k) -> _FakeSocket:  # type: ignore[no-untyped-def]
        s = _FakeSocket(*a, **k)
        created.append(s)
        return s

    monkeypatch.setattr(net.socket, "socket", _factory)
    net.detect_lan_ip()
    assert created and created[0].closed is True
