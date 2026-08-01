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
from curbcam.alerts.registry import CHANNELS, ChannelSpec
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
        # Iterating CHANNELS rather than a hard-coded list here is what stops a
        # newly-added channel from being fully configurable in the UI yet never
        # firing, which was the previous failure mode.
        for spec in CHANNELS:
            if (
                spec.enabled(s)
                and spec.is_configured(s)
                and self._due(spec.name, spec.cooldown_s(s), now)
            ):
                await self._fire(spec.name, self.send_to_channel(spec, s, data, text), now)

    async def send_to_channel(
        self, spec: ChannelSpec, s: AlertsSettings, data: dict[str, Any], text: str
    ) -> None:
        """Dispatch one payload to one channel.

        Shared with the test-alert endpoint so a test send goes down exactly the
        same path as a real one -- a test that used a separate code path could
        pass while real alerts fail.
        """
        if spec.name == "ntfy":
            await send_ntfy(self._client, s, text, data["url"])
        elif spec.name == "webhook":
            await send_webhook(self._client, s, data)
        elif spec.name == "mqtt":
            await self._publish_mqtt(s, data)
        else:  # pragma: no cover - registry and dispatcher out of sync
            raise ValueError(f"No sender wired for channel {spec.name!r}")

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
