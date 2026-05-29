"""Shared Jinja2 environment + template filters."""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from curbcam.web.units import format_speed

_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(_DIR / "templates"))
templates.env.filters["speed"] = format_speed
