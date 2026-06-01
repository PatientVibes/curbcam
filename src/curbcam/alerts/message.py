"""Pure builders for the alert message body (no I/O)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from curbcam.config.schema import AlertsSettings
from curbcam.localtime import to_local
from curbcam.web.units import kph_to_display


def build_payload(settings: AlertsSettings, event: dict[str, Any], units: str) -> dict[str, Any]:
    speed_kph = float(event["speed_kph"])
    base = settings.base_url.rstrip("/")
    return {
        "event_id": event.get("id"),
        "speed_kph": round(speed_kph, 1),
        "speed_display": round(kph_to_display(speed_kph, units), 1),
        "units": units,
        "direction": event.get("direction", ""),
        "ts_utc": event.get("ts_utc", ""),
        "url": f"{base}/events" if base else "",
    }


def build_text(payload: dict[str, Any], tz: dt.tzinfo = dt.UTC) -> str:
    base = f"{payload['speed_display']:.0f} {payload['units']} {payload['direction']}".strip()
    ts = payload.get("ts_utc", "")
    if ts:
        try:
            local = to_local(dt.datetime.fromisoformat(ts), tz)
            return f"{base} at {local.strftime('%H:%M')}"
        except ValueError:
            pass  # unparseable timestamp -> omit it rather than fail the alert
    return base
