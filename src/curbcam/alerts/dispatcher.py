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
