"""First-run wizard endpoints. /api/setup/* is gate-exempt."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from curbcam.web.deps import get_supervisor, issue_session, require_session
from curbcam.web.supervisor import Supervisor
from curbcam.web.templating import templates

router = APIRouter()


@router.post("/api/setup/password", response_class=HTMLResponse)
def setup_password(
    request: Request,
    password: str = Form(..., min_length=6),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    sup.auth.set_password(password)
    resp = templates.TemplateResponse(request, "setup/configure.html", {})
    issue_session(sup, resp)
    return resp


@router.post("/api/setup/camera", response_class=HTMLResponse)
async def setup_camera(
    source: str = Form(...),
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    raw = sup.config_store.load_raw()
    raw.setdefault("camera", {})["source"] = source
    sup.config_store.save_raw(raw)
    await run_in_threadpool(sup.restart)
    return HTMLResponse("Camera saved — preview below should update.")
