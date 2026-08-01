"""Declarative registry of alert channels.

Before this existed, adding a channel meant editing five files: schema.py,
defaults.py, settings_form.py, channels.py, and a hard-coded list inside
dispatcher.py. The last one was the easy one to miss -- a channel could be fully
configurable in the UI and simply never fire, with nothing to indicate why.

Now the dispatcher and the test-alert endpoint both iterate CHANNELS, so a new
channel is: implement the transport in channels.py, add its fields to schema.py +
defaults.py + settings_form.py (all three enforced by
tests/unit/config/test_settings_ui_coverage.py), and add one ChannelSpec here.

Each spec knows how to read its own enable flag, target and cooldown off
AlertsSettings, so the dispatcher does not need to know any channel's field
names.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from curbcam.config.schema import AlertsSettings


@dataclass(frozen=True)
class ChannelSpec:
    """One alert transport.

    name:      stable id, used for cooldown bookkeeping and in API responses.
    label:     human-facing name, shown in the UI and in test-alert results.
    enabled:   is this channel switched on?
    target:    the value that must be non-empty for the channel to be usable
               (topic / URL / broker host). Doubles as the "is it configured?"
               check and as the thing to name when it is missing.
    target_label: what to call that value when telling the user it is missing.
    cooldown_s:  minimum seconds between sends.
    """

    name: str
    label: str
    enabled: Callable[[AlertsSettings], bool]
    target: Callable[[AlertsSettings], str]
    target_label: str
    cooldown_s: Callable[[AlertsSettings], int]

    def is_configured(self, s: AlertsSettings) -> bool:
        return bool(self.target(s).strip())


CHANNELS: tuple[ChannelSpec, ...] = (
    ChannelSpec(
        name="ntfy",
        label="ntfy",
        enabled=lambda s: s.ntfy_enabled,
        target=lambda s: s.ntfy_topic,
        target_label="topic",
        cooldown_s=lambda s: s.ntfy_cooldown_s,
    ),
    ChannelSpec(
        name="webhook",
        label="Webhook",
        enabled=lambda s: s.webhook_enabled,
        target=lambda s: s.webhook_url,
        target_label="URL",
        cooldown_s=lambda s: s.webhook_cooldown_s,
    ),
    ChannelSpec(
        name="mqtt",
        label="MQTT",
        enabled=lambda s: s.mqtt_enabled,
        target=lambda s: s.mqtt_host,
        target_label="broker host",
        cooldown_s=lambda s: s.mqtt_cooldown_s,
    ),
)

CHANNELS_BY_NAME: dict[str, ChannelSpec] = {c.name: c for c in CHANNELS}

# Sender factories are supplied by the dispatcher, which owns the http client and
# the MQTT connection. Kept as a type alias so both the dispatcher and the
# test-alert route describe the same shape.
SenderFactory = Callable[[ChannelSpec, AlertsSettings, dict[str, Any], str], Awaitable[None]]
