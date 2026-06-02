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
        # Check paho's return code so a dropped/refused connection surfaces as an
        # exception (caught + logged by the dispatcher, and — importantly — the
        # channel's cooldown is NOT advanced, so the next event retries). Without
        # this, publish() to a dead broker no-ops and alerts vanish silently.
        info = self._client.publish(topic, payload)
        if getattr(info, "rc", 0) != 0:  # 0 == MQTT_ERR_SUCCESS
            raise RuntimeError(f"MQTT publish failed (rc={info.rc})")

    async def aclose(self) -> None:
        # loop_stop() joins paho's network thread and disconnect() does socket
        # I/O — both can block, so offload them off the event loop.
        if self._started:
            await asyncio.to_thread(self._stop)
            self._started = False

    def _stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()
