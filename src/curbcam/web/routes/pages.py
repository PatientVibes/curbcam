"""Server-rendered pages."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from curbcam.web.deps import get_supervisor, require_session
from curbcam.web.supervisor import Supervisor
from curbcam.web.templating import templates

router = APIRouter()


@router.get("/setup", response_class=HTMLResponse, response_model=None)
def setup_page(
    request: Request,
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse | RedirectResponse:
    # No session required — this is the entry point before any password exists.
    if sup.auth.has_password() and sup.calibrations.get_active() is not None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request,
        "setup/index.html",
        {"need_password": not sup.auth.has_password()},
    )


@router.get("/media/{path:path}")
def media(
    path: str,
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> FileResponse:
    """Serve event images behind the admin session (spec §6).

    A bare StaticFiles mount would expose private event JPEGs to anyone on
    the LAN once configured. This route requires a session and confirms the
    resolved file stays inside media_root (path-traversal guard).
    """
    root = sup.media_root.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(target)


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    units = sup.config_store.load().server.units
    events = sup.events.list_recent(limit=10)
    return templates.TemplateResponse(request, "dashboard.html", {"events": events, "units": units})


@router.get("/events", response_class=HTMLResponse)
def events_page(
    request: Request,
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    from curbcam.storage.repositories import EventFilter

    units = sup.config_store.load().server.units
    limit = 24
    rows = sup.events.query(EventFilter(), limit=limit)
    next_cursor = f"{rows[-1].ts_utc.isoformat()}|{rows[-1].id}" if len(rows) == limit else ""
    return templates.TemplateResponse(
        request,
        "events.html",
        {"events": rows, "units": units, "next_cursor": next_cursor, "query": ""},
    )


@router.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    from curbcam.web.settings_form import build_groups

    raw = sup.config_store.load_raw()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"groups": build_groups(raw), "tokens": sup.auth.list_stream_tokens(), "saved": False},
    )


@router.get("/setup/calibrate", response_class=HTMLResponse)
def calibrate_wizard(
    request: Request,
    _: None = Depends(require_session),
) -> HTMLResponse:
    return templates.TemplateResponse(request, "setup/calibrate.html", {})


@router.get("/setup/align", response_class=HTMLResponse)
def align_wizard(
    request: Request,
    _: None = Depends(require_session),
) -> HTMLResponse:
    return templates.TemplateResponse(request, "setup/align.html", {})
