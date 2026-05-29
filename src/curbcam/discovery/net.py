"""Best-effort primary LAN IPv4 detection."""

from __future__ import annotations

import socket


def detect_lan_ip() -> str:
    """Return this host's primary outbound IPv4, or '127.0.0.1' on failure.

    Opens a UDP socket and 'connects' it to a public address. UDP connect
    does not send any packet — it only makes the OS pick the source address
    of the interface that would route there, which we read back. This is the
    standard no-traffic way to learn the primary LAN IP for the startup
    banner + the mDNS A-record.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return str(s.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()
