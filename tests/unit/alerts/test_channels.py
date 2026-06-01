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
