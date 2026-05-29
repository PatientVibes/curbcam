"""Build settings field descriptors for the form (shared by GET + POST-error).

Each descriptor carries label/help (from config.defaults.FIELD_LABELS), the
current value, an input kind, and whether the field is shadowed by an env var
(rendered read-only). crop is excluded — it is set by the alignment wizard.
"""
from __future__ import annotations

import os
from typing import Any

from curbcam.config.defaults import FIELD_LABELS

PRIMARY: list[tuple[str, str]] = [
    ("camera.source", "text"),
    ("camera.resolution", "resolution"),
    ("camera.fps_target", "number"),
    ("server.units", "select:kph,mph"),
    ("server.min_event_speed_kph", "number"),
]
ADVANCED: list[tuple[str, str]] = [
    ("detector.min_area_px", "number"),
    ("detector.min_track_frames", "number"),
    ("detector.max_dist_px", "number"),
    ("retention.max_events_per_day", "number"),
    ("retention.max_total_disk_mb", "number"),
    ("server.log_level", "select:DEBUG,INFO,WARNING"),
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
    options = kind.split(":", 1)[1].split(",") if kind.startswith("select:") else []
    return {
        "key": dotted,
        "label": label,
        "help": help_text,
        "kind": "select" if kind.startswith("select:") else kind,
        "options": options,
        "value": _format_value(_get(raw, dotted), kind),
        "env": os.environ.get(_env_key(dotted)) is not None,
        "error": errors.get(dotted),
    }


def build_groups(
    raw: dict[str, Any], errors: dict[str, str] | None = None
) -> dict[str, list[dict[str, Any]]]:
    errors = errors or {}
    return {
        "primary": [_descriptor(raw, k, kind, errors) for k, kind in PRIMARY],
        "advanced": [_descriptor(raw, k, kind, errors) for k, kind in ADVANCED],
    }
