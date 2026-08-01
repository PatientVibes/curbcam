"""The 'Send test alert' button.

The point of these tests is that the button tells the truth: a success message
must mean the payload really went out over the configured transport, and a
failure must say something specific enough to act on. A test button that
optimistically reports success would be worse than not having one.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from curbcam.web.supervisor import Supervisor


def _login(client: TestClient, sup: Supervisor) -> None:
    """Bring the app out of first-run and establish a session.

    The gate treats the app as configured only once a password AND an active
    calibration exist, so both are needed before /settings stops redirecting.
    """
    sup.auth.set_password("x")
    sup.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": "x"})


def _set_alerts(sup: Supervisor, **overrides: Any) -> None:
    raw = sup.config_store.load_raw()
    raw.setdefault("alerts", {}).update(overrides)
    sup.config_store.save_raw(raw)


def test_unknown_channel_is_rejected(client: TestClient, supervisor: Supervisor) -> None:
    _login(client, supervisor)
    r = client.post("/api/alerts/test/carrier-pigeon")
    assert r.status_code == 200  # htmx fragment, outcome is in the markup
    assert "Unknown channel" in r.text
    assert "test-fail" in r.text


def test_unconfigured_channel_names_what_is_missing(
    client: TestClient, supervisor: Supervisor
) -> None:
    """An empty topic and a broken topic need different fixes, so they must not
    produce the same message."""
    _login(client, supervisor)
    _set_alerts(supervisor, ntfy_enabled=True, ntfy_topic="")
    r = client.post("/api/alerts/test/ntfy")
    assert "test-fail" in r.text
    assert "topic" in r.text.lower()


def test_requires_a_session_once_configured(client: TestClient, supervisor: Supervisor) -> None:
    """Unauthenticated callers must not be able to make the device emit traffic
    to an arbitrary configured webhook or MQTT broker.

    Configure the device (password + calibration) but do NOT log in: on an
    unconfigured device there is no password to check yet, so the meaningful
    assertion is that a configured device rejects a session-less caller.
    """
    supervisor.auth.set_password("x")
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    r = client.post("/api/alerts/test/ntfy", follow_redirects=False)
    assert r.status_code == 401


def test_successful_send_reports_success(
    client: TestClient, supervisor: Supervisor, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client, supervisor)
    _set_alerts(supervisor, enabled=True, ntfy_enabled=True, ntfy_topic="curbcam-test-topic")

    sent: list[tuple[str, str]] = []

    async def fake_send(spec: Any, s: Any, data: dict[str, Any], text: str) -> None:
        sent.append((spec.name, text))

    dispatcher = client.app.state.alert_dispatcher  # type: ignore[attr-defined]
    monkeypatch.setattr(dispatcher, "send_to_channel", fake_send)

    r = client.post("/api/alerts/test/ntfy")
    assert "test-ok" in r.text
    assert len(sent) == 1, "the endpoint must actually dispatch, not just claim it did"
    name, text = sent[0]
    assert name == "ntfy"
    # Marked as a test so a recipient cannot mistake it for a real vehicle.
    assert text.startswith("[TEST]")


def test_transport_failure_is_surfaced_not_swallowed(
    client: TestClient, supervisor: Supervisor, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wrong topic or unreachable broker must be visible in the UI -- silently
    reporting success is the exact failure this feature exists to prevent."""
    _login(client, supervisor)
    _set_alerts(supervisor, enabled=True, ntfy_enabled=True, ntfy_topic="curbcam-test-topic")

    async def boom(spec: Any, s: Any, data: dict[str, Any], text: str) -> None:
        raise RuntimeError("403 Forbidden from ntfy.sh")

    dispatcher = client.app.state.alert_dispatcher  # type: ignore[attr-defined]
    monkeypatch.setattr(dispatcher, "send_to_channel", boom)

    r = client.post("/api/alerts/test/ntfy")
    assert "test-fail" in r.text
    assert "403 Forbidden" in r.text


def test_send_works_while_channel_is_switched_off(
    client: TestClient, supervisor: Supervisor, monkeypatch: pytest.MonkeyPatch
) -> None:
    """You configure a channel before enabling it, so the test must not require
    the master switch -- but it should say the channel is still off."""
    _login(client, supervisor)
    _set_alerts(supervisor, enabled=False, ntfy_enabled=False, ntfy_topic="curbcam-test-topic")

    sent: list[str] = []

    async def fake_send(spec: Any, s: Any, data: dict[str, Any], text: str) -> None:
        sent.append(spec.name)

    dispatcher = client.app.state.alert_dispatcher  # type: ignore[attr-defined]
    monkeypatch.setattr(dispatcher, "send_to_channel", fake_send)

    r = client.post("/api/alerts/test/ntfy")
    assert "test-ok" in r.text
    assert sent == ["ntfy"]
    assert "switched off" in r.text


def test_every_registry_channel_has_a_button_on_the_settings_page(
    client: TestClient, supervisor: Supervisor
) -> None:
    """Guards the registry -> UI wiring: a channel added to CHANNELS must get a
    test button without anyone remembering to touch the template."""
    from curbcam.alerts.registry import CHANNELS

    _login(client, supervisor)
    html = client.get("/settings").text
    for spec in CHANNELS:
        assert f"/api/alerts/test/{spec.name}" in html, f"no test button rendered for {spec.name}"
