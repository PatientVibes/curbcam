"""Server-rendered pages."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from curbcam.web.deps import get_supervisor, require_session
from curbcam.web.supervisor import Supervisor
from curbcam.web.templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    units = sup.config_store.load().server.units
    events = sup.events.list_recent(limit=10)
    return templates.TemplateResponse(
        request, "dashboard.html", {"events": events, "units": units}
    )


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
    next_cursor = (
        f"{rows[-1].ts_utc.isoformat()}|{rows[-1].id}" if len(rows) == limit else ""
    )
    return templates.TemplateResponse(
        request,
        "events.html",
        {"events": rows, "units": units, "next_cursor": next_cursor, "query": ""},
    )
