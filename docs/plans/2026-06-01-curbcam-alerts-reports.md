# Alerts & Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add threshold alerts (ntfy + webhook + MQTT) and a server-rendered reports dashboard to curbcam, per `docs/specs/2026-06-01-curbcam-alerts-reports.md`.

**Architecture:** Two independent vertical slices sharing only the `events` table and the Settings form. **Alerts** = an `AlertsSettings` config block + an `AlertDispatcher` asyncio task that subscribes to the existing `EventBus`, caches config (refreshed on the `settings_changed` envelope), and fans qualifying events out to per-channel senders with per-channel cooldown. **Reports** = pure-SQL aggregation methods on `EventRepo` + `/reports` + `/api/reports` routes rendering inline-SVG charts (no frontend build step).

**Tech Stack:** FastAPI, htmx, Jinja2, SQLAlchemy/SQLite, Pydantic v2, httpx (async), paho-mqtt (new), pytest (+pytest-asyncio, asyncio_mode=auto).

---

## File structure

**Create:**
- `src/curbcam/alerts/__init__.py` — package marker.
- `src/curbcam/alerts/message.py` — pure payload/text builders.
- `src/curbcam/alerts/channels.py` — `send_ntfy`, `send_webhook`, `MqttPublisher`.
- `src/curbcam/alerts/dispatcher.py` — `AlertDispatcher` (subscribe loop, qualifying rule, cooldown, config cache).
- `src/curbcam/web/routes/reports.py` — `/reports` + `/api/reports`.
- `src/curbcam/web/templates/reports.html` — full page.
- `src/curbcam/web/templates/partials/reports_dashboard.html` — dashboard partial (htmx-swapped).
- `tests/unit/alerts/__init__.py`, `tests/unit/alerts/test_message.py`, `tests/unit/alerts/test_dispatcher.py`, `tests/unit/alerts/test_channels.py`
- `tests/unit/storage/test_reports.py`
- `tests/integration/web/test_reports_page.py`
- `tests/integration/web/test_alerts_settings.py`

**Modify:**
- `src/curbcam/config/schema.py` — add `AlertsSettings`, mount on `Settings`.
- `src/curbcam/config/defaults.py` — `FIELD_LABELS` rows for alert fields.
- `src/curbcam/web/settings_form.py` — `ALERTS` group + `bool` field kind.
- `src/curbcam/web/routes/settings.py` — `_coerce` boolean branch + `BOOLEAN_KEYS`.
- `src/curbcam/web/app.py` — start/stop the dispatcher in `lifespan`; register reports router.
- `src/curbcam/storage/repositories.py` — reports aggregations + `_percentile`.
- `src/curbcam/web/templates/base.html` — `/reports` nav link.
- `pyproject.toml` — add `paho-mqtt`.

---

# SLICE 1 — ALERTS

## Task 1: `AlertsSettings` config model + labels

**Files:**
- Modify: `src/curbcam/config/schema.py`
- Modify: `src/curbcam/config/defaults.py`
- Test: `tests/unit/config/test_schema.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/config/test_schema.py`:

```python
def test_alerts_defaults_are_off_and_safe() -> None:
    from curbcam.config.schema import AlertsSettings, Settings

    a = Settings().alerts
    assert a.enabled is False
    assert a.ntfy_enabled is False and a.webhook_enabled is False and a.mqtt_enabled is False
    assert a.ntfy_server == "https://ntfy.sh"
    assert a.mqtt_port == 1883
    assert a.mqtt_cooldown_s == 0  # 0 = no throttle, every qualifying event
    assert a.ntfy_cooldown_s == 60
    assert a.base_url == "http://curbcam.local:8080"
    # cooldown / threshold validation
    with pytest.raises(ValueError):
        AlertsSettings(min_speed_kph=-1.0)
    with pytest.raises(ValueError):
        AlertsSettings(ntfy_cooldown_s=-1)


def test_alerts_env_override_shadows_field(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from curbcam.config.schema import Settings

    monkeypatch.setenv("CURBCAM_ALERTS__WEBHOOK_URL", "https://example.test/hook")
    monkeypatch.setenv("CURBCAM_ALERTS__ENABLED", "true")
    s = Settings()
    assert s.alerts.webhook_url == "https://example.test/hook"
    assert s.alerts.enabled is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/config/test_schema.py -q`
Expected: FAIL (`ImportError: cannot import name 'AlertsSettings'`).

- [ ] **Step 3: Add the model**

In `src/curbcam/config/schema.py`, add the class (above `class Settings`):

```python
class AlertsSettings(BaseModel):
    enabled: bool = False
    min_speed_kph: float = Field(default=0.0, ge=0)
    base_url: str = "http://curbcam.local:8080"

    ntfy_enabled: bool = False
    ntfy_server: str = "https://ntfy.sh"
    ntfy_topic: str = ""
    ntfy_cooldown_s: int = Field(default=60, ge=0)

    webhook_enabled: bool = False
    webhook_url: str = ""
    webhook_cooldown_s: int = Field(default=60, ge=0)

    mqtt_enabled: bool = False
    mqtt_host: str = ""
    mqtt_port: int = Field(default=1883, ge=1, le=65535)
    mqtt_topic: str = "curbcam/events"
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_cooldown_s: int = Field(default=0, ge=0)
```

Mount it on `Settings` (after `server: ServerSettings = ServerSettings()`):

```python
    alerts: AlertsSettings = AlertsSettings()
```

- [ ] **Step 4: Add labels**

In `src/curbcam/config/defaults.py`, add to `FIELD_LABELS` (inside the dict):

```python
    "alerts.enabled": (
        "Enable alerts",
        "Master switch. When off, no channel fires regardless of its own setting.",
    ),
    "alerts.min_speed_kph": (
        "Alert speed (km/h)",
        "Only vehicles at or above this speed (in km/h) trigger an alert. Independent "
        "of the recording threshold; usually set higher.",
    ),
    "alerts.base_url": (
        "Site URL",
        "Base URL used for the click-through link in alerts, e.g. "
        "http://curbcam.local:8080. Leave blank to send no link.",
    ),
    "alerts.ntfy_enabled": ("ntfy: enable", "Send alerts to an ntfy topic (phone push)."),
    "alerts.ntfy_server": ("ntfy: server", "ntfy server base URL. Default https://ntfy.sh."),
    "alerts.ntfy_topic": ("ntfy: topic", "The ntfy topic to publish to. Required for ntfy."),
    "alerts.ntfy_cooldown_s": (
        "ntfy: cooldown (s)",
        "Minimum seconds between ntfy alerts. 0 sends one per qualifying event.",
    ),
    "alerts.webhook_enabled": ("Webhook: enable", "POST a JSON body to a URL of your choice."),
    "alerts.webhook_url": ("Webhook: URL", "Destination URL for the JSON POST. Required."),
    "alerts.webhook_cooldown_s": (
        "Webhook: cooldown (s)",
        "Minimum seconds between webhook posts. 0 sends one per qualifying event.",
    ),
    "alerts.mqtt_enabled": ("MQTT: enable", "Publish a JSON body to an MQTT broker."),
    "alerts.mqtt_host": ("MQTT: host", "Broker hostname or IP. Required for MQTT."),
    "alerts.mqtt_port": ("MQTT: port", "Broker port. Default 1883."),
    "alerts.mqtt_topic": ("MQTT: topic", "Topic to publish to. Default curbcam/events."),
    "alerts.mqtt_username": ("MQTT: username", "Broker username (optional)."),
    "alerts.mqtt_password": ("MQTT: password", "Broker password (optional)."),
    "alerts.mqtt_cooldown_s": (
        "MQTT: cooldown (s)",
        "Minimum seconds between MQTT publishes. 0 (default) publishes every "
        "qualifying event — the right setting for Home Assistant.",
    ),
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/config/test_schema.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/curbcam/config/schema.py src/curbcam/config/defaults.py tests/unit/config/test_schema.py
git commit -m "feat(config): AlertsSettings model + field labels"
```

---

## Task 2: Boolean settings round-trip (form + coercion)

Booleans render as `true/false` selects (always submit a value) and coerce to real YAML bools, so a channel toggled off actually persists `false`.

**Files:**
- Modify: `src/curbcam/web/settings_form.py`
- Modify: `src/curbcam/web/routes/settings.py`
- Test: `tests/unit/web/test_settings_form.py` (create), `tests/integration/web/test_alerts_settings.py` (create)

- [ ] **Step 1: Write the failing unit test**

Create `tests/unit/web/test_settings_form.py`:

```python
from curbcam.web.settings_form import build_groups


def test_alerts_group_present_with_bool_as_select() -> None:
    raw = {"alerts": {"enabled": True, "ntfy_enabled": False}}
    groups = build_groups(raw)
    assert "alerts" in groups
    by_key = {f["key"]: f for f in groups["alerts"]}
    enabled = by_key["alerts.enabled"]
    assert enabled["kind"] == "select"
    assert enabled["options"] == ["true", "false"]
    assert enabled["value"] == "true"  # normalized lowercase so the <option> matches
    assert by_key["alerts.ntfy_enabled"]["value"] == "false"
```

- [ ] **Step 2: Write the failing coercion test**

Create `tests/unit/web/test_settings_coerce.py`:

```python
from curbcam.web.routes.settings import _coerce


def test_coerce_boolean_keys_to_real_bool() -> None:
    assert _coerce("alerts.enabled", "true") is True
    assert _coerce("alerts.enabled", "false") is False
    assert _coerce("alerts.mqtt_enabled", "false") is False


def test_coerce_passes_non_bool_through() -> None:
    assert _coerce("alerts.ntfy_topic", "street") == "street"
    assert _coerce("camera.resolution", "1280x720") == [1280, 720]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/web/test_settings_form.py tests/unit/web/test_settings_coerce.py -q`
Expected: FAIL (`alerts` group missing; `_coerce` returns the string `"true"`).

- [ ] **Step 4: Implement the form group + bool kind**

In `src/curbcam/web/settings_form.py`, add the group list after `ADVANCED`:

```python
ALERTS: list[tuple[str, str]] = [
    ("alerts.enabled", "bool"),
    ("alerts.min_speed_kph", "number"),
    ("alerts.base_url", "text"),
    ("alerts.ntfy_enabled", "bool"),
    ("alerts.ntfy_server", "text"),
    ("alerts.ntfy_topic", "text"),
    ("alerts.ntfy_cooldown_s", "number"),
    ("alerts.webhook_enabled", "bool"),
    ("alerts.webhook_url", "text"),
    ("alerts.webhook_cooldown_s", "number"),
    ("alerts.mqtt_enabled", "bool"),
    ("alerts.mqtt_host", "text"),
    ("alerts.mqtt_port", "number"),
    ("alerts.mqtt_topic", "text"),
    ("alerts.mqtt_username", "text"),
    ("alerts.mqtt_password", "text"),
    ("alerts.mqtt_cooldown_s", "number"),
]
```

Replace `_descriptor` so a `bool` kind becomes a normalized `true/false` select:

```python
def _descriptor(
    raw: dict[str, Any], dotted: str, kind: str, errors: dict[str, str]
) -> dict[str, Any]:
    label, help_text = FIELD_LABELS.get(dotted, (dotted, ""))
    base = {
        "key": dotted,
        "label": label,
        "help": help_text,
        "env": os.environ.get(_env_key(dotted)) is not None,
        "error": errors.get(dotted),
    }
    if kind == "bool":
        # Render as a true/false <select>: a select always submits a value,
        # whereas an unchecked checkbox submits nothing and would leave the
        # boolean stuck at its previous value (settings.py overlays submitted
        # keys onto the loaded raw config).
        truthy = str(_get(raw, dotted)).lower() == "true"
        return {**base, "kind": "select", "options": ["true", "false"],
                "value": "true" if truthy else "false"}
    options = kind.split(":", 1)[1].split(",") if kind.startswith("select:") else []
    return {**base, "kind": "select" if kind.startswith("select:") else kind,
            "options": options, "value": _format_value(_get(raw, dotted), kind)}
```

Add the group to `build_groups`'s return dict:

```python
    return {
        "primary": [_descriptor(raw, k, kind, errors) for k, kind in PRIMARY],
        "advanced": [_descriptor(raw, k, kind, errors) for k, kind in ADVANCED],
        "alerts": [_descriptor(raw, k, kind, errors) for k, kind in ALERTS],
    }
```

- [ ] **Step 5: Implement the coercion branch**

In `src/curbcam/web/routes/settings.py`, add a module constant and a branch in `_coerce`:

```python
BOOLEAN_KEYS = {
    "alerts.enabled",
    "alerts.ntfy_enabled",
    "alerts.webhook_enabled",
    "alerts.mqtt_enabled",
}


def _coerce(key: str, value: str) -> object:
    if key == "camera.resolution":
        w, h = value.lower().split("x", 1)
        return [int(w), int(h)]
    if key in BOOLEAN_KEYS:
        return value == "true"  # persist a real YAML bool, not the string "true"
    return value  # Pydantic coerces numeric strings; selects/text pass through
```

- [ ] **Step 6: Run unit tests to verify they pass**

Run: `uv run pytest tests/unit/web/test_settings_form.py tests/unit/web/test_settings_coerce.py -q`
Expected: PASS.

- [ ] **Step 7: Write the integration toggle test (the bug Gemini caught)**

Create `tests/integration/web/test_alerts_settings.py`:

```python
def _configure(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": password})


def _full_form(overrides: dict[str, str]) -> dict[str, str]:
    # The settings POST overlays submitted keys; send the alert fields the form
    # renders so a save reflects exactly the on-screen state.
    base = {
        "camera.source": "file:./x",
        "camera.resolution": "640x480",
        "camera.fps_target": "15",
        "server.units": "kph",
        "server.min_event_speed_kph": "5",
        "detector.min_area_px": "800",
        "detector.min_track_frames": "5",
        "detector.max_dist_px": "100",
        "retention.max_events_per_day": "500",
        "retention.max_total_disk_mb": "5000",
        "server.log_level": "INFO",
        "alerts.enabled": "false",
        "alerts.min_speed_kph": "0",
        "alerts.base_url": "http://curbcam.local:8080",
        "alerts.ntfy_enabled": "false",
        "alerts.ntfy_server": "https://ntfy.sh",
        "alerts.ntfy_topic": "",
        "alerts.ntfy_cooldown_s": "60",
        "alerts.webhook_enabled": "false",
        "alerts.webhook_url": "",
        "alerts.webhook_cooldown_s": "60",
        "alerts.mqtt_enabled": "false",
        "alerts.mqtt_host": "",
        "alerts.mqtt_port": "1883",
        "alerts.mqtt_topic": "curbcam/events",
        "alerts.mqtt_username": "",
        "alerts.mqtt_password": "",
        "alerts.mqtt_cooldown_s": "0",
    }
    base.update(overrides)
    return base


def test_settings_page_renders_alerts_group(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert 'name="alerts.enabled"' in resp.text
    assert "Alerts" in resp.text  # fieldset legend (group name capitalized)


def test_alert_boolean_can_be_toggled_off(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    # Enable, then disable, and assert the on-disk YAML reflects the OFF state.
    client.post("/api/settings", data=_full_form({"alerts.enabled": "true"}))
    assert supervisor.config_store.load().alerts.enabled is True
    client.post("/api/settings", data=_full_form({"alerts.enabled": "false"}))
    assert supervisor.config_store.load().alerts.enabled is False
    raw = supervisor.config_store.load_raw()
    assert raw["alerts"]["enabled"] is False  # real bool, not the string "true"
```

- [ ] **Step 8: Run the integration test**

Run: `uv run pytest tests/integration/web/test_alerts_settings.py -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/curbcam/web/settings_form.py src/curbcam/web/routes/settings.py tests/unit/web/test_settings_form.py tests/unit/web/test_settings_coerce.py tests/integration/web/test_alerts_settings.py
git commit -m "feat(settings): alert fields with boolean true/false selects that persist"
```

---

## Task 3: Alert message/payload builders

**Files:**
- Create: `src/curbcam/alerts/__init__.py` (empty), `src/curbcam/alerts/message.py`
- Test: `tests/unit/alerts/__init__.py` (empty), `tests/unit/alerts/test_message.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/alerts/test_message.py`:

```python
from curbcam.alerts.message import build_payload, build_text
from curbcam.config.schema import AlertsSettings

EVENT = {"id": 7, "speed_kph": 61.2, "direction": "L2R", "ts_utc": "2026-06-01T19:14:02"}


def test_build_payload_converts_to_display_units_and_links() -> None:
    s = AlertsSettings(base_url="http://cam.local:8080")
    p = build_payload(s, EVENT, "mph")
    assert p["event_id"] == 7
    assert p["speed_kph"] == 61.2
    assert p["speed_display"] == 38.0  # 61.2 / 1.609344 -> 38.0
    assert p["units"] == "mph"
    assert p["direction"] == "L2R"
    assert p["url"] == "http://cam.local:8080/events"


def test_build_payload_blank_base_url_omits_link() -> None:
    p = build_payload(AlertsSettings(base_url=""), EVENT, "kph")
    assert p["url"] == ""


def test_build_text_is_speed_units_direction() -> None:
    s = AlertsSettings(base_url="")
    assert build_text(build_payload(s, EVENT, "mph")) == "38 mph L2R"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/alerts/test_message.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

Create `src/curbcam/alerts/__init__.py` (empty file). Create `src/curbcam/alerts/message.py`:

```python
"""Pure builders for the alert message body (no I/O)."""

from __future__ import annotations

from typing import Any

from curbcam.config.schema import AlertsSettings
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


def build_text(payload: dict[str, Any]) -> str:
    return f"{payload['speed_display']:.0f} {payload['units']} {payload['direction']}".strip()
```

Create `tests/unit/alerts/__init__.py` (empty).

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/alerts/test_message.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/curbcam/alerts/__init__.py src/curbcam/alerts/message.py tests/unit/alerts/__init__.py tests/unit/alerts/test_message.py
git commit -m "feat(alerts): message/payload builders"
```

---

## Task 4: Channel senders (ntfy, webhook, MQTT)

**Files:**
- Modify: `pyproject.toml`
- Create: `src/curbcam/alerts/channels.py`
- Test: `tests/unit/alerts/test_channels.py`

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, add to `[project].dependencies`:

```toml
    "paho-mqtt>=2.1",
```

Run: `uv pip install -e ".[dev]"`
Expected: installs `paho-mqtt`.

- [ ] **Step 2: Write the failing test**

Create `tests/unit/alerts/test_channels.py`:

```python
import json

import pytest

from curbcam.alerts.channels import MqttPublisher, send_ntfy, send_webhook
from curbcam.config.schema import AlertsSettings


class _Resp:
    def raise_for_status(self) -> None:
        pass


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def post(self, url, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append({"url": url, **kwargs})
        return _Resp()


@pytest.mark.asyncio
async def test_send_ntfy_posts_to_server_slash_topic_with_click_header() -> None:
    c = _FakeClient()
    s = AlertsSettings(ntfy_server="https://ntfy.sh/", ntfy_topic="mystreet")
    await send_ntfy(c, s, "38 mph L2R", "http://cam.local:8080/events")
    call = c.calls[0]
    assert call["url"] == "https://ntfy.sh/mystreet"
    assert call["headers"]["Click"] == "http://cam.local:8080/events"
    assert call["content"] == b"38 mph L2R"


@pytest.mark.asyncio
async def test_send_webhook_posts_json() -> None:
    c = _FakeClient()
    s = AlertsSettings(webhook_url="https://example.test/hook")
    payload = {"event_id": 1, "speed_display": 38.0}
    await send_webhook(c, s, payload)
    assert c.calls[0]["url"] == "https://example.test/hook"
    assert c.calls[0]["json"] == payload


def test_mqtt_publisher_uses_loop_start_and_nonblocking_publish() -> None:
    # Inject a fake paho client so no broker/network is needed.
    published: list[tuple[str, str]] = []
    events: list[str] = []

    class _FakePaho:
        def username_pw_set(self, u, p):  # type: ignore[no-untyped-def]
            events.append("auth")

        def connect(self, host, port):  # type: ignore[no-untyped-def]
            events.append(f"connect:{host}:{port}")

        def loop_start(self):  # type: ignore[no-untyped-def]
            events.append("loop_start")

        def publish(self, topic, payload):  # type: ignore[no-untyped-def]
            published.append((topic, payload))

        def loop_stop(self):  # type: ignore[no-untyped-def]
            events.append("loop_stop")

        def disconnect(self):  # type: ignore[no-untyped-def]
            events.append("disconnect")

    pub = MqttPublisher("broker", 1883, "u", "p", client=_FakePaho())
    import asyncio

    asyncio.run(pub.publish("curbcam/events", json.dumps({"a": 1})))
    assert "connect:broker:1883" in events and "loop_start" in events
    assert published == [("curbcam/events", '{"a": 1}')]
    pub.close()
    assert "loop_stop" in events and "disconnect" in events
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/unit/alerts/test_channels.py -q`
Expected: FAIL (module missing).

- [ ] **Step 4: Implement**

Create `src/curbcam/alerts/channels.py`:

```python
"""Alert transports. HTTP channels are async; MQTT is offloaded so paho's
blocking calls never run on the event loop."""

from __future__ import annotations

import asyncio
from typing import Any

from curbcam.config.schema import AlertsSettings

_HTTP_TIMEOUT_S = 5.0


async def send_ntfy(client: Any, s: AlertsSettings, text: str, url: str) -> None:
    headers: dict[str, str] = {"Title": "curbcam: vehicle detected"}
    if url:
        headers["Click"] = url
    endpoint = f"{s.ntfy_server.rstrip('/')}/{s.ntfy_topic}"
    resp = await client.post(
        endpoint, content=text.encode("utf-8"), headers=headers, timeout=_HTTP_TIMEOUT_S
    )
    resp.raise_for_status()


async def send_webhook(client: Any, s: AlertsSettings, payload: dict[str, Any]) -> None:
    resp = await client.post(s.webhook_url, json=payload, timeout=_HTTP_TIMEOUT_S)
    resp.raise_for_status()


class MqttPublisher:
    """Wraps a paho-mqtt client. connect() is offloaded via asyncio.to_thread;
    publish() is non-blocking (paho's network thread handles delivery once
    loop_start() is running), so nothing blocks the asyncio event loop."""

    def __init__(
        self, host: str, port: int, username: str, password: str, *, client: Any | None = None
    ) -> None:
        if client is None:
            import paho.mqtt.client as mqtt  # lazy: only import when MQTT is used

            client = mqtt.Client()
        self._client = client
        self._host = host
        self._port = port
        if username:
            self._client.username_pw_set(username, password)
        self._started = False

    async def publish(self, topic: str, payload: str) -> None:
        if not self._started:
            await asyncio.to_thread(self._client.connect, self._host, self._port)
            self._client.loop_start()
            self._started = True
        self._client.publish(topic, payload)

    def close(self) -> None:
        if self._started:
            self._client.loop_stop()
            self._client.disconnect()
            self._started = False
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/unit/alerts/test_channels.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/curbcam/alerts/channels.py tests/unit/alerts/test_channels.py
git commit -m "feat(alerts): ntfy/webhook/MQTT channel senders (+paho-mqtt dep)"
```

---

## Task 5: `AlertDispatcher` (qualifying rule, cooldown, config cache)

**Files:**
- Create: `src/curbcam/alerts/dispatcher.py`
- Test: `tests/unit/alerts/test_dispatcher.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/alerts/test_dispatcher.py`:

```python
import pytest

from curbcam.alerts.dispatcher import AlertDispatcher
from curbcam.config.schema import AlertsSettings, Settings


class _FakeStore:
    def __init__(self, alerts: AlertsSettings, units: str = "kph") -> None:
        self._s = Settings().model_copy(
            update={"alerts": alerts, "server": Settings().server.model_copy(update={"units": units})}
        )

    def set(self, alerts: AlertsSettings) -> None:
        self._s = self._s.model_copy(update={"alerts": alerts})

    def load(self) -> Settings:
        return self._s


class _Resp:
    def raise_for_status(self) -> None:
        pass


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def post(self, url, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(url)
        return _Resp()

    async def aclose(self) -> None:
        pass


def _disp(store, client, clock):  # type: ignore[no-untyped-def]
    return AlertDispatcher(store, bus=None, http_client=client, clock=clock)


EVENT = {"id": 1, "speed_kph": 50.0, "direction": "L2R", "ts_utc": "2026-06-01T00:00:00"}


@pytest.mark.asyncio
async def test_no_fire_when_disabled() -> None:
    store = _FakeStore(AlertsSettings(enabled=False, ntfy_enabled=True, ntfy_topic="t"))
    c = _FakeClient()
    await _disp(store, c, lambda: 0.0).handle(EVENT)
    assert c.calls == []


@pytest.mark.asyncio
async def test_no_fire_below_threshold() -> None:
    store = _FakeStore(
        AlertsSettings(enabled=True, min_speed_kph=60.0, ntfy_enabled=True, ntfy_topic="t")
    )
    c = _FakeClient()
    await _disp(store, c, lambda: 0.0).handle(EVENT)
    assert c.calls == []


@pytest.mark.asyncio
async def test_fires_ntfy_when_qualifying() -> None:
    store = _FakeStore(
        AlertsSettings(enabled=True, ntfy_enabled=True, ntfy_topic="t", ntfy_server="https://n")
    )
    c = _FakeClient()
    await _disp(store, c, lambda: 0.0).handle(EVENT)
    assert c.calls == ["https://n/t"]


@pytest.mark.asyncio
async def test_cooldown_suppresses_then_allows() -> None:
    store = _FakeStore(
        AlertsSettings(enabled=True, ntfy_enabled=True, ntfy_topic="t", ntfy_cooldown_s=60)
    )
    c = _FakeClient()
    now = {"t": 0.0}
    d = _disp(store, c, lambda: now["t"])
    await d.handle(EVENT)          # fires
    now["t"] = 30.0
    await d.handle(EVENT)          # within cooldown -> suppressed
    now["t"] = 61.0
    await d.handle(EVENT)          # past cooldown -> fires
    assert len(c.calls) == 2


@pytest.mark.asyncio
async def test_cooldown_zero_fires_every_event() -> None:
    store = _FakeStore(
        AlertsSettings(enabled=True, webhook_enabled=True, webhook_url="https://h", webhook_cooldown_s=0)
    )
    c = _FakeClient()
    d = _disp(store, c, lambda: 0.0)
    await d.handle(EVENT)
    await d.handle(EVENT)
    assert c.calls == ["https://h", "https://h"]


@pytest.mark.asyncio
async def test_channel_failure_is_isolated() -> None:
    class _BoomClient(_FakeClient):
        async def post(self, url, **kwargs):  # type: ignore[no-untyped-def]
            if "boom" in url:
                raise RuntimeError("down")
            return await super().post(url, **kwargs)

    store = _FakeStore(
        AlertsSettings(
            enabled=True,
            ntfy_enabled=True, ntfy_topic="boom", ntfy_server="https://n",
            webhook_enabled=True, webhook_url="https://ok",
        )
    )
    c = _BoomClient()
    await _disp(store, c, lambda: 0.0).handle(EVENT)
    assert c.calls == ["https://ok"]  # webhook still fired despite ntfy failure


@pytest.mark.asyncio
async def test_refresh_reloads_cached_config() -> None:
    store = _FakeStore(AlertsSettings(enabled=False))
    c = _FakeClient()
    d = _disp(store, c, lambda: 0.0)
    await d.handle(EVENT)
    assert c.calls == []
    store.set(AlertsSettings(enabled=True, webhook_enabled=True, webhook_url="https://h"))
    d.refresh()
    await d.handle(EVENT)
    assert c.calls == ["https://h"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/alerts/test_dispatcher.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

Create `src/curbcam/alerts/dispatcher.py`:

```python
"""Subscribes to the EventBus and fans qualifying events out to alert channels.

Runs as an asyncio task in the web app's lifespan. Config is cached and only
re-read when a `settings_changed` envelope arrives, so the event loop never does
synchronous YAML I/O per event.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from curbcam.alerts.channels import MqttPublisher, send_ntfy, send_webhook
from curbcam.alerts.message import build_payload, build_text
from curbcam.config.schema import AlertsSettings

log = logging.getLogger(__name__)


class AlertDispatcher:
    def __init__(
        self,
        config_store: Any,
        bus: Any,
        *,
        http_client: Any | None = None,
        mqtt_factory: Callable[..., Any] = MqttPublisher,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._store = config_store
        self._bus = bus
        self._clock = clock
        self._mqtt_factory = mqtt_factory
        self._owns_client = http_client is None
        if http_client is None:
            import httpx

            http_client = httpx.AsyncClient()
        self._client = http_client
        self._last_fired: dict[str, float] = {}
        self._mqtt: Any | None = None
        self._mqtt_sig: tuple | None = None
        self.refresh()

    # -- config cache --
    def refresh(self) -> None:
        full = self._store.load()
        self._settings: AlertsSettings = full.alerts
        self._units: str = full.server.units

    # -- subscribe loop (run as an asyncio task) --
    async def run(self) -> None:
        queue = self._bus.subscribe()
        try:
            while True:
                env = await queue.get()
                if env.kind == "settings_changed":
                    self.refresh()
                elif env.kind == "event":
                    await self.handle(env.payload)
        finally:
            self._bus.unsubscribe(queue)

    async def handle(self, payload: dict[str, Any]) -> None:
        s = self._settings
        if not s.enabled:
            return
        try:
            speed_kph = float(payload["speed_kph"])
        except (KeyError, TypeError, ValueError):
            return
        if speed_kph < s.min_speed_kph:
            return
        data = build_payload(s, payload, self._units)
        text = build_text(data)
        now = self._clock()
        if s.ntfy_enabled and s.ntfy_topic and self._due("ntfy", s.ntfy_cooldown_s, now):
            await self._fire("ntfy", send_ntfy(self._client, s, text, data["url"]), now)
        if s.webhook_enabled and s.webhook_url and self._due("webhook", s.webhook_cooldown_s, now):
            await self._fire("webhook", send_webhook(self._client, s, data), now)
        if s.mqtt_enabled and s.mqtt_host and self._due("mqtt", s.mqtt_cooldown_s, now):
            await self._fire("mqtt", self._publish_mqtt(s, data), now)

    def _due(self, name: str, cooldown_s: int, now: float) -> bool:
        last = self._last_fired.get(name)
        return last is None or (now - last) >= cooldown_s

    async def _fire(self, name: str, coro: Any, now: float) -> None:
        try:
            await coro
            self._last_fired[name] = now
        except Exception:
            log.warning("alert channel %s failed", name, exc_info=True)

    async def _publish_mqtt(self, s: AlertsSettings, data: dict[str, Any]) -> None:
        sig = (s.mqtt_host, s.mqtt_port, s.mqtt_username, s.mqtt_password)
        if self._mqtt is None or self._mqtt_sig != sig:
            if self._mqtt is not None:
                self._mqtt.close()
            self._mqtt = self._mqtt_factory(s.mqtt_host, s.mqtt_port, s.mqtt_username, s.mqtt_password)
            self._mqtt_sig = sig
        await self._mqtt.publish(s.mqtt_topic, json.dumps(data))

    async def aclose(self) -> None:
        if self._mqtt is not None:
            self._mqtt.close()
        if self._owns_client:
            await self._client.aclose()
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/alerts/test_dispatcher.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/curbcam/alerts/dispatcher.py tests/unit/alerts/test_dispatcher.py
git commit -m "feat(alerts): AlertDispatcher with per-channel cooldown + config cache"
```

---

## Task 6: Wire the dispatcher into the app lifespan

**Files:**
- Modify: `src/curbcam/web/app.py`
- Test: `tests/integration/web/test_alerts_dispatch.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/integration/web/test_alerts_dispatch.py`:

```python
import datetime as dt

import pytest

from curbcam.config.schema import AlertsSettings
from curbcam.pipeline.events import EventBus, EventEnvelope


@pytest.mark.asyncio
async def test_dispatcher_fires_webhook_on_event_envelope(supervisor) -> None:  # type: ignore[no-untyped-def]
    # Configure alerts on, webhook enabled, in the supervisor's config store.
    raw = supervisor.config_store.load_raw()
    raw["alerts"] = AlertsSettings(
        enabled=True, webhook_enabled=True, webhook_url="https://hook.test/x", min_speed_kph=0.0
    ).model_dump(mode="json")
    supervisor.config_store.save_raw(raw)

    from curbcam.alerts.dispatcher import AlertDispatcher

    class _Resp:
        def raise_for_status(self) -> None:
            pass

    class _Client:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def post(self, url, **kwargs):  # type: ignore[no-untyped-def]
            self.calls.append(url)
            return _Resp()

        async def aclose(self) -> None:
            pass

    client = _Client()
    d = AlertDispatcher(supervisor.config_store, supervisor.bus, http_client=client, clock=lambda: 0.0)
    d.refresh()
    await d.handle(
        {"id": 1, "speed_kph": 80.0, "direction": "L2R", "ts_utc": dt.datetime.now().isoformat()}
    )
    assert client.calls == ["https://hook.test/x"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/integration/web/test_alerts_dispatch.py -q`
Expected: PASS already (this exercises the dispatcher directly). If PASS, proceed — it locks the supervisor/config-store contract the lifespan wiring relies on.

> Note: this test validates the dispatcher against the real `ConfigStore`/`Supervisor`. The lifespan wiring below has no separate unit test (it is exercised by every existing web integration test booting the app); Step 3 must not break app startup.

- [ ] **Step 3: Wire into lifespan**

In `src/curbcam/web/app.py`, modify `lifespan`:

```python
    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        from curbcam.alerts.dispatcher import AlertDispatcher

        supervisor.bus.bind_loop(asyncio.get_running_loop())
        supervisor.start()
        stats_task = asyncio.create_task(_stats_loop(supervisor))
        dispatcher = AlertDispatcher(supervisor.config_store, supervisor.bus)
        alerts_task = asyncio.create_task(dispatcher.run())
        try:
            yield
        finally:
            stats_task.cancel()
            alerts_task.cancel()
            await dispatcher.aclose()
            supervisor.stop()
```

- [ ] **Step 4: Run the full web integration suite to confirm startup is intact**

Run: `uv run pytest tests/integration/web -q`
Expected: PASS (all existing tests + the new ones).

- [ ] **Step 5: Commit**

```bash
git add src/curbcam/web/app.py tests/integration/web/test_alerts_dispatch.py
git commit -m "feat(alerts): start the AlertDispatcher in the app lifespan"
```

---

# SLICE 2 — REPORTS

## Task 7: Report aggregations on `EventRepo`

**Files:**
- Modify: `src/curbcam/storage/repositories.py`
- Test: `tests/unit/storage/test_reports.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/storage/test_reports.py`:

```python
import datetime as dt
from pathlib import Path

import pytest

from curbcam.storage import Database
from curbcam.storage.models import Base
from curbcam.storage.repositories import EventRepo


@pytest.fixture
def repo(tmp_path: Path) -> EventRepo:
    db = Database.for_sqlite_path(tmp_path / "r.sqlite")
    Base.metadata.create_all(db.engine)
    r = EventRepo(db)
    # Six events on 2026-05-28, speeds 20..45, hours 8,8,9,9,10,10.
    for i, (hour, speed, direction) in enumerate(
        [(8, 20.0, "L2R"), (8, 25.0, "R2L"), (9, 30.0, "L2R"),
         (9, 35.0, "R2L"), (10, 40.0, "L2R"), (10, 45.0, "R2L")]
    ):
        r.save(
            ts_utc=dt.datetime(2026, 5, 28, hour, i, 0),
            speed_kph=speed, direction=direction, frame_count=10, track_len_px=200,
            image_path=f"e_{i}.jpg", thumb_path=f"t_{i}.jpg", calibration_id=None,
        )
    return r


def test_summary_percentiles(repo: EventRepo) -> None:
    s = repo.summary(None)
    assert s.count == 6
    assert s.median_kph == pytest.approx(32.5)   # interp between 30 and 35
    assert s.p85_kph == pytest.approx(41.25)      # interp 40..45 at 0.85
    assert s.max_kph == pytest.approx(45.0)


def test_summary_empty_window(repo: EventRepo) -> None:
    s = repo.summary(dt.datetime(2030, 1, 1))
    assert s.count == 0 and s.median_kph == 0.0 and s.max_kph == 0.0


def test_speed_histogram_buckets(repo: EventRepo) -> None:
    # 10-kph bins -> {20:2 (20,25), 30:2 (30,35), 40:2 (40,45)}
    assert repo.speed_histogram(None, 10.0) == {20: 2, 30: 2, 40: 2}


def test_by_hour_returns_24_slots(repo: EventRepo) -> None:
    by_hour = repo.by_hour(None)
    assert len(by_hour) == 24
    assert by_hour[8] == 2 and by_hour[9] == 2 and by_hour[10] == 2
    assert by_hour[0] == 0


def test_daily_counts(repo: EventRepo) -> None:
    assert repo.daily_counts(None) == [("2026-05-28", 6)]


def test_by_direction(repo: EventRepo) -> None:
    bd = repo.by_direction(None)
    assert bd["L2R"][0] == 3 and bd["R2L"][0] == 3      # counts
    assert bd["L2R"][1] == pytest.approx(30.0)           # median of 20,30,40
    assert bd["R2L"][1] == pytest.approx(35.0)           # median of 25,35,45
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/storage/test_reports.py -q`
Expected: FAIL (methods missing).

- [ ] **Step 3: Implement**

In `src/curbcam/storage/repositories.py`, add imports and a `ReportSummary` dataclass near the top (after the existing imports):

```python
import math

from sqlalchemy import func
```

Add the dataclass after `EventFilter`:

```python
@dataclass
class ReportSummary:
    count: int
    median_kph: float
    p85_kph: float
    max_kph: float


def _percentile(sorted_vals: list[float], pct: float) -> float:
    """Linear-interpolated percentile (numpy 'linear' method)."""
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return sorted_vals[int(k)]
    return sorted_vals[lo] * (hi - k) + sorted_vals[hi] * (k - lo)
```

Add these methods to `EventRepo`:

```python
    def _speeds_since(self, start: dt.datetime | None, direction: str | None = None) -> list[float]:
        with self._db.session() as s:
            q = s.query(Event.speed_kph)
            if start is not None:
                q = q.filter(Event.ts_utc >= start)
            if direction is not None:
                q = q.filter(Event.direction == direction)
            return sorted(float(r[0]) for r in q.all())

    def summary(self, start: dt.datetime | None) -> ReportSummary:
        speeds = self._speeds_since(start)
        if not speeds:
            return ReportSummary(0, 0.0, 0.0, 0.0)
        return ReportSummary(
            count=len(speeds),
            median_kph=_percentile(speeds, 50),
            p85_kph=_percentile(speeds, 85),
            max_kph=speeds[-1],
        )

    def speed_histogram(self, start: dt.datetime | None, bin_kph: float) -> dict[int, int]:
        out: dict[int, int] = {}
        for v in self._speeds_since(start):
            b = int(v // bin_kph) * int(bin_kph)
            out[b] = out.get(b, 0) + 1
        return out

    def by_hour(self, start: dt.datetime | None) -> list[int]:
        with self._db.session() as s:
            q = s.query(func.strftime("%H", Event.ts_utc), func.count())
            if start is not None:
                q = q.filter(Event.ts_utc >= start)
            counts = {int(hr): n for hr, n in q.group_by(func.strftime("%H", Event.ts_utc)).all()}
        return [counts.get(h, 0) for h in range(24)]

    def daily_counts(self, start: dt.datetime | None) -> list[tuple[str, int]]:
        with self._db.session() as s:
            day = func.strftime("%Y-%m-%d", Event.ts_utc)
            q = s.query(day, func.count())
            if start is not None:
                q = q.filter(Event.ts_utc >= start)
            return [(d, n) for d, n in q.group_by(day).order_by(day).all()]

    def by_direction(self, start: dt.datetime | None) -> dict[str, tuple[int, float]]:
        out: dict[str, tuple[int, float]] = {}
        for direction in ("L2R", "R2L"):
            speeds = self._speeds_since(start, direction)
            out[direction] = (len(speeds), _percentile(speeds, 50) if speeds else 0.0)
        return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/storage/test_reports.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/curbcam/storage/repositories.py tests/unit/storage/test_reports.py
git commit -m "feat(storage): report aggregations (summary/histogram/by-hour/daily/direction)"
```

---

## Task 8: Window parsing + report context builder

Builds display-ready geometry so the templates stay dumb.

**Files:**
- Create: `src/curbcam/web/reports.py`
- Test: `tests/unit/web/test_reports_context.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/web/test_reports_context.py`:

```python
import datetime as dt

from curbcam.web.reports import window_start


def test_window_start_mappings() -> None:
    now = dt.datetime(2026, 6, 1, 15, 30, 0)
    assert window_start("today", now) == dt.datetime(2026, 6, 1, 0, 0, 0)
    assert window_start("7d", now) == now - dt.timedelta(days=7)
    assert window_start("30d", now) == now - dt.timedelta(days=30)
    assert window_start("all", now) is None
    assert window_start("garbage", now) == now - dt.timedelta(days=7)  # default 7d
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/web/test_reports_context.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

Create `src/curbcam/web/reports.py`:

```python
"""Report window parsing + view-model assembly for the reports dashboard."""

from __future__ import annotations

import datetime as dt
from typing import Any

from curbcam.web.supervisor import Supervisor
from curbcam.web.units import kph_to_display

WINDOWS = ("today", "7d", "30d", "all")
_BIN_KPH = 5.0


def window_start(window: str, now: dt.datetime) -> dt.datetime | None:
    if window == "today":
        return dt.datetime.combine(now.date(), dt.time.min)
    if window == "30d":
        return now - dt.timedelta(days=30)
    if window == "all":
        return None
    return now - dt.timedelta(days=7)  # 7d is the default for "7d" and anything unknown


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def build_context(sup: Supervisor, window: str) -> dict[str, Any]:
    if window not in WINDOWS:
        window = "7d"
    units = sup.config_store.load().server.units
    start = window_start(window, _now_utc())
    repo = sup.events

    summary = repo.summary(start)
    bins = repo.speed_histogram(start, _BIN_KPH)
    by_hour = repo.by_hour(start)
    daily = repo.daily_counts(start)
    by_dir = repo.by_direction(start)

    def disp(kph: float) -> float:
        return round(kph_to_display(kph, units), 1)

    # Histogram bars (display-unit bucket labels, % heights for inline SVG).
    hist_max = max(bins.values(), default=0)
    histogram = [
        {
            "label": f"{disp(lo):.0f}",
            "count": bins[lo],
            "pct": (bins[lo] / hist_max * 100) if hist_max else 0,
        }
        for lo in sorted(bins)
    ]

    hour_max = max(by_hour, default=0)
    hours = [
        {"hour": h, "count": c, "pct": (c / hour_max * 100) if hour_max else 0}
        for h, c in enumerate(by_hour)
    ]
    busiest_hour = max(range(24), key=lambda h: by_hour[h]) if summary.count else None

    # Daily trend polyline points over a 100x100 viewBox.
    day_max = max((n for _, n in daily), default=0)
    n = len(daily)
    trend_points = " ".join(
        f"{(i / (n - 1) * 100) if n > 1 else 0:.1f},{100 - (cnt / day_max * 100 if day_max else 0):.1f}"
        for i, (_, cnt) in enumerate(daily)
    )

    return {
        "window": window,
        "windows": WINDOWS,
        "units": units,
        "summary": {
            "count": summary.count,
            "median": disp(summary.median_kph),
            "p85": disp(summary.p85_kph),
            "max": disp(summary.max_kph),
        },
        "histogram": histogram,
        "hours": hours,
        "busiest_hour": busiest_hour,
        "daily": [{"date": d, "count": c} for d, c in daily],
        "trend_points": trend_points,
        "by_direction": {
            "L2R": {"count": by_dir["L2R"][0], "median": disp(by_dir["L2R"][1])},
            "R2L": {"count": by_dir["R2L"][0], "median": disp(by_dir["R2L"][1])},
        },
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/web/test_reports_context.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/curbcam/web/reports.py tests/unit/web/test_reports_context.py
git commit -m "feat(web): reports window parsing + dashboard view-model"
```

---

## Task 9: Reports routes, templates, and nav link

**Files:**
- Create: `src/curbcam/web/routes/reports.py`
- Create: `src/curbcam/web/templates/reports.html`
- Create: `src/curbcam/web/templates/partials/reports_dashboard.html`
- Modify: `src/curbcam/web/app.py`, `src/curbcam/web/templates/base.html`
- Test: `tests/integration/web/test_reports_page.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/integration/web/test_reports_page.py`:

```python
import datetime as dt


def _configure(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": password})


def _seed(supervisor, n: int = 5) -> None:  # type: ignore[no-untyped-def]
    for i in range(n):
        supervisor.events.save(
            ts_utc=dt.datetime.now() - dt.timedelta(hours=i),
            speed_kph=30.0 + i, direction="L2R" if i % 2 else "R2L",
            frame_count=10, track_len_px=200,
            image_path=f"e_{i}.jpg", thumb_path=f"t_{i}.jpg", calibration_id=None,
        )


def test_reports_requires_session(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("pw")
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    resp = client.get("/reports", follow_redirects=False)
    assert resp.status_code == 401


def test_reports_page_renders_with_data(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    _seed(supervisor)
    resp = client.get("/reports")
    assert resp.status_code == 200
    assert "Reports" in resp.text
    assert "<svg" in resp.text  # inline-SVG charts present


def test_reports_partial_window_switch(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    _seed(supervisor)
    resp = client.get("/api/reports?window=30d")
    assert resp.status_code == 200
    assert "<svg" in resp.text


def test_reports_empty_state(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    resp = client.get("/reports")
    assert resp.status_code == 200
    assert "No events" in resp.text


def test_reports_nav_link_present(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    resp = client.get("/")
    assert 'href="/reports"' in resp.text
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/integration/web/test_reports_page.py -q`
Expected: FAIL (route + templates missing).

- [ ] **Step 3: Implement the routes**

Create `src/curbcam/web/routes/reports.py`:

```python
"""Reports dashboard: summary + charts over a selectable window."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from curbcam.web.deps import get_supervisor, require_session
from curbcam.web.reports import build_context
from curbcam.web.supervisor import Supervisor
from curbcam.web.templating import templates

router = APIRouter()


@router.get("/reports", response_class=HTMLResponse)
def reports_page(
    request: Request,
    window: str = "7d",
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    return templates.TemplateResponse(request, "reports.html", build_context(sup, window))


@router.get("/api/reports", response_class=HTMLResponse)
def reports_partial(
    request: Request,
    window: str = "7d",
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "partials/reports_dashboard.html", build_context(sup, window)
    )
```

Register it in `src/curbcam/web/app.py` — add the import to the `from curbcam.web.routes import (...)` block and include the router beside the others:

```python
    app.include_router(reports.router)
```

(Add `reports` to the imported names.)

- [ ] **Step 4: Create the partial template**

Create `src/curbcam/web/templates/partials/reports_dashboard.html`:

```html
<div id="reports-dashboard">
  <div class="report-windows">
    {% for w in windows %}
    <button type="button" class="btn {% if w == window %}btn-primary{% endif %}"
            hx-get="/api/reports?window={{ w }}" hx-target="#reports-dashboard" hx-swap="outerHTML">
      {{ {"today": "Today", "7d": "7 days", "30d": "30 days", "all": "All"}[w] }}
    </button>
    {% endfor %}
  </div>

  {% if summary.count == 0 %}
  <p class="empty">No events in this window yet.</p>
  {% else %}
  <div class="cards report-summary">
    <div class="card"><span class="stat">{{ summary.count }}</span><span class="label">vehicles</span></div>
    <div class="card"><span class="stat">{{ summary.median }}</span><span class="label">median {{ units }}</span></div>
    <div class="card"><span class="stat">{{ summary.p85 }}</span><span class="label">85th pct {{ units }}</span></div>
    <div class="card"><span class="stat">{{ summary.max }}</span><span class="label">max {{ units }}</span></div>
  </div>

  <h3>Speed distribution ({{ units }})</h3>
  <svg class="chart bars" viewBox="0 0 {{ histogram|length * 10 }} 100" preserveAspectRatio="none" role="img">
    {% for b in histogram %}
    <rect x="{{ loop.index0 * 10 + 1 }}" y="{{ 100 - b.pct }}" width="8" height="{{ b.pct }}"></rect>
    {% endfor %}
  </svg>
  <div class="axis">{% for b in histogram %}<span>{{ b.label }}</span>{% endfor %}</div>

  <h3>By hour of day{% if busiest_hour is not none %} — busiest {{ busiest_hour }}:00{% endif %}</h3>
  <svg class="chart bars" viewBox="0 0 240 100" preserveAspectRatio="none" role="img">
    {% for h in hours %}
    <rect x="{{ h.hour * 10 + 1 }}" y="{{ 100 - h.pct }}" width="8" height="{{ h.pct }}"></rect>
    {% endfor %}
  </svg>

  {% if daily|length > 1 %}
  <h3>Daily volume</h3>
  <svg class="chart trend" viewBox="0 0 100 100" preserveAspectRatio="none" role="img">
    <polyline points="{{ trend_points }}" fill="none" stroke="currentColor" stroke-width="1"></polyline>
  </svg>
  {% endif %}

  <h3>By direction</h3>
  <table class="report-directions">
    <tr><th></th><th>Vehicles</th><th>Median {{ units }}</th></tr>
    <tr><td>Left → right</td><td>{{ by_direction.L2R.count }}</td><td>{{ by_direction.L2R.median }}</td></tr>
    <tr><td>Right → left</td><td>{{ by_direction.R2L.count }}</td><td>{{ by_direction.R2L.median }}</td></tr>
  </table>
  {% endif %}
</div>
```

- [ ] **Step 5: Create the page template**

Create `src/curbcam/web/templates/reports.html`:

```html
{% extends "base.html" %}
{% block title %} · Reports{% endblock %}
{% block content %}
<h1>Reports</h1>
{% include "partials/reports_dashboard.html" %}
{% endblock %}
```

- [ ] **Step 6: Add the nav link**

In `src/curbcam/web/templates/base.html`, add after the Events link:

```html
    <a href="/reports">Reports</a>
```

- [ ] **Step 7: Run to verify it passes**

Run: `uv run pytest tests/integration/web/test_reports_page.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/curbcam/web/routes/reports.py src/curbcam/web/templates/reports.html src/curbcam/web/templates/partials/reports_dashboard.html src/curbcam/web/app.py src/curbcam/web/templates/base.html tests/integration/web/test_reports_page.py
git commit -m "feat(reports): /reports dashboard with inline-SVG charts + nav link"
```

---

## Task 10: Full gate — suite, lint, types, docs

**Files:**
- Modify: `README.md` (document alerts + reports + the new dep)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -q`
Expected: all pass (no new skips/failures vs. the pre-feature baseline).

- [ ] **Step 2: Lint + format**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: clean. Fix any findings and re-run.

- [ ] **Step 3: Type-check**

Run: `uv run mypy src`
Expected: clean. Common fixes: annotate the dispatcher's injected `Any` params (already `Any`), ensure `ReportSummary` import path is correct.

- [ ] **Step 4: Update the README**

In `README.md`, add a short "Alerts" subsection (under the post-setup feature list) describing ntfy/webhook/MQTT + the threshold/cooldown model, and a "Reports" mention next to the Events history. Note MQTT requires a broker. No new install step (paho-mqtt ships in the image).

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: document alerts + reports"
```

- [ ] **Step 6: Open the PR**

```bash
git push -u origin feat/alerts-reports
gh pr create --base main --title "feat: alerts (ntfy/webhook/MQTT) + reports dashboard" --body "Implements docs/specs/2026-06-01-curbcam-alerts-reports.md. See plan docs/plans/2026-06-01-curbcam-alerts-reports.md."
```

---

## Self-review notes (addressed during authoring)

- **Spec coverage:** §4 alerts (Tasks 1–6), §5 reports (Tasks 7–9), §6 dep (Task 4), §7 testing (each task's tests + Task 10 gate). Honest-precision (§5.5) handled by `_BIN_KPH=5` bucketing + whole-unit summary rounding in `build_context`.
- **Boolean round-trip (Gemini CRITICAL #1):** Task 2 — `true/false` select + `_coerce` bool branch + explicit toggle-off integration test.
- **MQTT non-blocking (Gemini CRITICAL #2):** Task 4 — `loop_start()` + `connect()` via `asyncio.to_thread`, non-blocking `publish()`.
- **Config cache (Gemini IMPORTANT):** Task 5 — `refresh()` on `settings_changed`, no per-event YAML read.
- **Type consistency:** `AlertDispatcher(http_client=…, clock=…)`, `refresh()`, `handle()`, `aclose()`, `MqttPublisher(host, port, username, password, *, client=…)`, `ReportSummary(count, median_kph, p85_kph, max_kph)`, `build_context(sup, window)`, `window_start(window, now)` — names consistent across tasks.
