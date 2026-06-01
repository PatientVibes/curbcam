"""Convert stored naive-UTC timestamps to a configured local timezone.

Events are stored as naive UTC. The Reports page and alert messages present
times to the user, so they convert through the ``server.timezone`` setting (an
IANA name). The live event feed localizes in the browser instead, so it does not
use this module.

ZoneInfo (not the OS local zone) is used deliberately: it reads the bundled
``tzdata`` package, so conversion works inside the slim Docker image without an
OS timezone database. An empty or unknown name falls back to UTC rather than
raising, so a typo in Settings never breaks the dashboard.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def zone(tz_name: str) -> dt.tzinfo:
    """Resolve an IANA timezone name to a tzinfo, falling back to UTC."""
    if not tz_name:
        return dt.UTC
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        return dt.UTC


def to_local(naive_utc: dt.datetime, tz: dt.tzinfo) -> dt.datetime:
    """Interpret a naive datetime as UTC and convert it to ``tz``."""
    return naive_utc.replace(tzinfo=dt.UTC).astimezone(tz)
