"""Shared Jinja2 environment + template filters."""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from curbcam.alerts.registry import CHANNELS
from curbcam.web.units import format_speed

_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(_DIR / "templates"))
templates.env.filters["speed"] = format_speed

# Registered as a global rather than passed per-render: the settings form is
# rendered from three separate call sites (the settings page and both branches of
# the save handler), and threading a context key through all three is precisely
# the kind of drift this change set exists to remove. Adding a channel to the
# registry now surfaces its test button everywhere, with no further edits.
templates.env.globals["alert_channels"] = CHANNELS
