"""Settings save: parse form -> validate -> save raw YAML -> graceful restart.

Env-shadowed fields are read-only in the form and therefore not posted, so
the saved YAML never bakes in an env value (spec §5).
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse
from markupsafe import escape
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


@router.post("/api/tokens", response_class=HTMLResponse)
def mint_token(
    request: Request,
    label: str = Form(...),
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    token_id, raw_token = sup.auth.mint_stream_token(label)
    # Escape the user-supplied label to prevent stored XSS (the admin is the
    # only writer, but defense-in-depth is cheap). raw_token is server-minted.
    safe_label = escape(label)
    # Show the raw token once; it is never retrievable again.
    html = (
        f'<li data-token-id="{token_id}">{safe_label} '
        f'<code class="token-once">{raw_token}</code> '
        f'<button hx-delete="/api/tokens/{token_id}" '
        f'hx-target="closest li" hx-swap="outerHTML">Revoke</button></li>'
    )
    return HTMLResponse(html)


@router.delete("/api/tokens/{token_id}")
def revoke_token(
    token_id: str,
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> Response:
    sup.auth.revoke_stream_token(token_id)
    return Response(status_code=200)


@router.post("/api/events/purge")
def purge_events(
    days: int = Form(...),
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> Response:
    cutoff = dt.datetime.now(dt.UTC).replace(tzinfo=None) - dt.timedelta(days=days)
    # Delete rows AND their media files — a privacy button that left the JPEGs
    # on disk would defeat its purpose (spec §15).
    for rel in sup.events.delete_older_than(cutoff):
        (sup.media_root / rel).unlink(missing_ok=True)
    return Response(status_code=204)
