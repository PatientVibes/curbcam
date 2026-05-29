"""In-process mDNS publisher (spec §3.2).

Advertises curbcam as an `_http._tcp` service with server name
`curbcam.local.`, so `http://curbcam.local:<port>` resolves on the LAN.
Replaces the avahi-in-container approach from the original design (§11.3):
host networking is required for multicast either way, and an in-process
publisher needs no D-Bus daemon and is unit-testable.

The Zeroconf instance is injectable so tests assert the ServiceInfo without
touching the network. In production, start() lazily creates a real one.
"""

from __future__ import annotations

import socket
from typing import Any

from zeroconf import ServiceInfo, Zeroconf

_SERVICE_TYPE = "_http._tcp.local."
_NAME = "curbcam"


class MDNSPublisher:
    def __init__(self, ip: str, port: int, *, zeroconf: Any = None) -> None:
        self._ip = ip
        self._port = port
        self._zc: Any = zeroconf
        self._info: ServiceInfo | None = None

    def _build_info(self) -> ServiceInfo:
        return ServiceInfo(
            _SERVICE_TYPE,
            f"{_NAME}.{_SERVICE_TYPE}",
            addresses=[socket.inet_aton(self._ip)],
            port=self._port,
            server=f"{_NAME}.local.",
        )

    def start(self) -> None:
        if self._zc is None:
            self._zc = Zeroconf()
        self._info = self._build_info()
        self._zc.register_service(self._info)

    def stop(self) -> None:
        if self._zc is None:
            return
        if self._info is not None:
            self._zc.unregister_service(self._info)
            self._info = None
        self._zc.close()
        self._zc = None
