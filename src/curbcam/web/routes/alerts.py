"""Send a test alert to one channel, so alert config can be verified from the UI.

Before this existed, the only way to find out whether your ntfy topic, webhook
URL or MQTT broker was right was to wait for a real vehicle to exceed the alert
threshold. A typo meant silence, and silence is indistinguishable from "no cars
went past". For a feature whose entire value is a notification arriving on your
phone, that was the biggest gap in the no-code story.

The test send deliberately reuses the live AlertDispatcher and its
send_to_channel path, so a passing test proves the real path works -- not a
parallel one that happens to be configured correctly.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from markupsafe import escape

from curbcam.alerts.message import build_payload, build_text
from curbcam.alerts.registry import CHANNELS_BY_NAME
from curbcam.localtime import now_utc, zone
from curbcam.web.deps import get_supervisor, require_session
from curbcam.web.supervisor import Supervisor

router = APIRouter()

# A recognisable, obviously-synthetic sample. 42 km/h is fast enough to look like
# a real reading but is not presented as one -- the text says TEST so nobody
# mistakes a verification ping for an actual vehicle.
_SAMPLE_SPEED_KPH = 42.0


def _result(ok: bool, message: str) -> HTMLResponse:
    css = "test-ok" if ok else "test-fail"
    icon = "OK" if ok else "Failed"
    return HTMLResponse(
        f'<span class="alert-test-result {css}">{icon} — {escape(message)}</span>',
        # Always 200: this is an htmx fragment swapped into the page, and htmx
        # ignores 4xx/5xx bodies by default. The outcome is carried in the markup
        # rather than the status code so failures are actually shown to the user.
        status_code=200,
    )


@router.post("/api/alerts/test/{channel}", response_class=HTMLResponse)
async def test_alert(
    channel: str,
    request: Request,
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    spec = CHANNELS_BY_NAME.get(channel)
    if spec is None:
        return _result(False, f"Unknown channel {channel!r}.")

    settings = sup.config_store.load()
    alerts = settings.alerts

    # Report configuration problems distinctly from delivery failures. "Topic is
    # empty" and "ntfy.sh returned 403" need different fixes, and lumping them
    # together as "failed" would send someone looking in the wrong place.
    if not spec.is_configured(alerts):
        return _result(False, f"No {spec.target_label} set for {spec.label}. Save one first.")

    dispatcher = getattr(request.app.state, "alert_dispatcher", None)
    if dispatcher is None:
        return _result(False, "Alert dispatcher is not running.")

    # Test sends bypass alerts.enabled, the per-channel enable flag, the speed
    # threshold and the cooldown ON PURPOSE: you are trying to verify credentials
    # and reachability, and being told "nothing happened because the master switch
    # is off" is not useful when the switch is the thing you are about to turn on.
    payload: dict[str, Any] = {
        "id": 0,
        "speed_kph": _SAMPLE_SPEED_KPH,
        "direction": "L2R",
        "ts_utc": now_utc().isoformat(),
    }
    data = build_payload(alerts, payload, settings.server.units)
    # Build the real message body, then mark it as a test. Using build_text rather
    # than a bespoke string means the test exercises the same formatting (units,
    # timezone) a real alert would, so a misconfigured timezone shows up here too.
    text = "[TEST] " + build_text(data, zone(settings.server.timezone))

    try:
        await dispatcher.send_to_channel(spec, alerts, data, text)
    except Exception as exc:
        # The exception text is the most useful thing we have (HTTP status, DNS
        # failure, MQTT rc). Truncated so a huge upstream body cannot wreck the
        # layout, and escaped because it may contain remote-controlled content.
        detail = str(exc) or exc.__class__.__name__
        return _result(False, detail[:300])

    note = "" if alerts.enabled and spec.enabled(alerts) else " (channel is currently switched off)"
    return _result(True, f"Test sent to {spec.label}.{note}")
