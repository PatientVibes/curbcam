"""Build settings field descriptors for the form (shared by GET + POST-error).

Each descriptor carries label/help (from config.defaults.FIELD_LABELS), the
current value, an input kind, and whether the field is shadowed by an env var
(rendered read-only). crop is excluded — it is set by the alignment wizard.
"""

from __future__ import annotations

import os
from typing import Any

from curbcam.config.defaults import FIELD_LABELS
from curbcam.config.schema import Settings


def _boolean_keys() -> frozenset[str]:
    """Dotted keys of every bool field, read from the Pydantic schema so the
    form (true/false select) and the save path (_coerce) share one source of
    truth — no hand-maintained list to drift from the model."""
    out: set[str] = set()
    for section, field in Settings.model_fields.items():
        sub_fields = getattr(field.annotation, "model_fields", None)
        if sub_fields:
            for name, info in sub_fields.items():
                if info.annotation is bool:
                    out.add(f"{section}.{name}")
    return frozenset(out)


# Single source of truth for "which settings are booleans", consumed here (to
# render a true/false <select>) and by routes.settings._coerce (to persist a
# real YAML bool).
BOOLEAN_KEYS = _boolean_keys()

PRIMARY: list[tuple[str, str]] = [
    ("camera.source", "camera-source"),
    ("camera.resolution", "resolution"),
    ("camera.fps_target", "number"),
    ("server.units", "select:kph,mph"),
    ("server.min_event_speed_kph", "number"),
    ("server.timezone", "text"),
]
ADVANCED: list[tuple[str, str]] = [
    ("detector.min_area_px", "number"),
    ("detector.min_track_frames", "number"),
    ("detector.max_dist_px", "number"),
    ("retention.max_events_per_day", "number"),
    ("retention.max_total_disk_mb", "number"),
    ("server.log_level", "select:DEBUG,INFO,WARNING"),
]
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


def _env_key(dotted: str) -> str:
    section, field = dotted.split(".", 1)
    return f"CURBCAM_{section.upper()}__{field.upper()}"


def _get(raw: dict[str, Any], dotted: str) -> Any:
    section, field = dotted.split(".", 1)
    return raw.get(section, {}).get(field)


def _format_value(value: Any, kind: str) -> str:
    if kind == "resolution" and isinstance(value, (list, tuple)) and len(value) == 2:
        return f"{value[0]}x{value[1]}"
    return "" if value is None else str(value)


def _descriptor(
    raw: dict[str, Any], dotted: str, kind: str, errors: dict[str, str]
) -> dict[str, Any]:
    label, help_text = FIELD_LABELS.get(dotted, (dotted, ""))
    env_var = _env_key(dotted)
    base = {
        "key": dotted,
        "label": label,
        "help": help_text,
        "env": os.environ.get(env_var) is not None,
        # Surfaced in the template so a read-only field explains *which* variable
        # is holding it and how to take back control. Without this the field is
        # simply un-editable with no stated cause -- a dead end for anyone who
        # set it once in docker-compose and later forgot.
        "env_var": env_var,
        "error": errors.get(dotted),
    }
    if dotted in BOOLEAN_KEYS:
        # Render as a true/false <select>: a select always submits a value,
        # whereas an unchecked checkbox submits nothing and would leave the
        # boolean stuck at its previous value (settings.py overlays submitted
        # keys onto the loaded raw config).
        truthy = str(_get(raw, dotted)).lower() == "true"
        return {
            **base,
            "kind": "select",
            "options": ["true", "false"],
            "value": "true" if truthy else "false",
        }
    options = kind.split(":", 1)[1].split(",") if kind.startswith("select:") else []
    return {
        **base,
        "kind": "select" if kind.startswith("select:") else kind,
        "options": options,
        "value": _format_value(_get(raw, dotted), kind),
    }


def build_groups(
    raw: dict[str, Any], errors: dict[str, str] | None = None
) -> dict[str, list[dict[str, Any]]]:
    errors = errors or {}
    return {
        "primary": [_descriptor(raw, k, kind, errors) for k, kind in PRIMARY],
        "advanced": [_descriptor(raw, k, kind, errors) for k, kind in ADVANCED],
        "alerts": [_descriptor(raw, k, kind, errors) for k, kind in ALERTS],
    }
