"""Process-level discovery: LAN-IP detection + in-process mDNS publishing.

Kept out of web/ — discovery is a deployment concern, orchestrated by the
CLI (spec §3), never imported by request handlers.
"""

from curbcam.discovery.mdns import MDNSPublisher
from curbcam.discovery.net import detect_lan_ip

__all__ = ["MDNSPublisher", "detect_lan_ip"]
