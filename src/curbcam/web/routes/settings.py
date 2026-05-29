"""Settings save: parse form -> validate -> save raw YAML -> graceful restart.

Env-shadowed fields are read-only in the form and therefore not posted, so
the saved YAML never bakes in an env value (spec §5).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from curbcam.config.schema import Settings
from curbcam.web.deps import get_supervisor, require_session
from curbcam.web.settings_form import build_groups
from curbcam.web.supervisor import Supervisor
from curbcam.web.templating import templates

router = APIRouter()


def _set_nested(d: dict[str, Any], dotted: str, value: object) -> None:
    section, field = dotted.split(".", 1)
    d.setdefault(section, {})[field] = value


def _coerce(key: str, value: str) -> object:
    if key == "camera.resolution":
        w, h = value.lower().split("x", 1)
        return [int(w), int(h)]
    return value  # Pydantic coerces numeric strings; selects/text pass through


@router.post("/api/settings", response_class=HTMLResponse)
async def save_settings(
    request: Request,
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    form = await request.form()
    raw = sup.config_store.load_raw()
    for key, value in form.items():
        if "." in key:
            try:
                _set_nested(raw, key, _coerce(key, str(value)))
            except ValueError:
                pass  # malformed resolution surfaces as a validation error below

    try:
        Settings.model_validate(raw)
    except ValidationError as exc:
        errors: dict[str, str] = {}
        for e in exc.errors():
            dotted = ".".join(str(p) for p in e["loc"][:2])
            errors[dotted] = e["msg"]
        return templates.TemplateResponse(
            request,
            "partials/settings_form.html",
            {"groups": build_groups(raw, errors), "saved": False},
            status_code=422,
        )

    sup.config_store.save_raw(raw)
    await run_in_threadpool(sup.restart)
    return templates.TemplateResponse(
        request,
        "partials/settings_form.html",
        {"groups": build_groups(raw), "saved": True},
    )
