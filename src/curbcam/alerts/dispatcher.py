"""Subscribes to the EventBus and fans qualifying events out to alert channels.

Runs as an asyncio task in the web app's lifespan. Config is cached and only
re-read when a `settings_changed` envelope arrives, so the event loop never does
synchronous YAML I/O per event.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
from collections.abc import Callable
from typing import Any

from curbcam.alerts.channels import MqttPublisher, send_ntfy, send_webhook
from curbcam.alerts.message import build_payload, build_text
from curbcam.config.schema import AlertsSettings
from curbcam.localtime import zone

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
        self._mqtt_sig: tuple[str, int, str, str] | None = None
        self.refresh()

    # -- config cache --
    def refresh(self) -> None:
        full = self._store.load()
        self._settings: AlertsSettings = full.alerts
        self._units: str = full.server.units
        self._tz: dt.tzinfo = zone(full.server.timezone)

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
        text = build_text(data, self._tz)
        now = self._clock()
        # (name, channel-on, required-target, cooldown, coroutine factory). The
        # factory defers building the coroutine until we actually fire, so no
        # unawaited coroutine is created for a skipped channel.
        channels: list[tuple[str, bool, str, int, Callable[[], Any]]] = [
            (
                "ntfy",
                s.ntfy_enabled,
                s.ntfy_topic,
                s.ntfy_cooldown_s,
                lambda: send_ntfy(self._client, s, text, data["url"]),
            ),
            (
                "webhook",
                s.webhook_enabled,
                s.webhook_url,
                s.webhook_cooldown_s,
                lambda: send_webhook(self._client, s, data),
            ),
            (
                "mqtt",
                s.mqtt_enabled,
                s.mqtt_host,
                s.mqtt_cooldown_s,
                lambda: self._publish_mqtt(s, data),
            ),
        ]
        for name, enabled, target, cooldown_s, make in channels:
            if enabled and target and self._due(name, cooldown_s, now):
                await self._fire(name, make(), now)

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
                await self._mqtt.aclose()
            self._mqtt = self._mqtt_factory(
                s.mqtt_host, s.mqtt_port, s.mqtt_username, s.mqtt_password
            )
            self._mqtt_sig = sig
        await self._mqtt.publish(s.mqtt_topic, json.dumps(data))

    async def aclose(self) -> None:
        if self._mqtt is not None:
            await self._mqtt.aclose()
        if self._owns_client:
            await self._client.aclose()
