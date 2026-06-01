"""Reports dashboard: summary + charts over a selectable window."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from curbcam.web.deps import get_supervisor, require_session
from curbcam.web.reports import build_context
from curbcam.web.supervisor import Supervisor
from curbcam.web.templating import templates

router = APIRouter()


@router.get("/reports", response_class=HTMLResponse)
def reports_page(
    request: Request,
    window: str = "7d",
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    return templates.TemplateResponse(request, "reports.html", build_context(sup, window))


@router.get("/api/reports", response_class=HTMLResponse)
def reports_partial(
    request: Request,
    window: str = "7d",
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "partials/reports_dashboard.html", build_context(sup, window)
    )
