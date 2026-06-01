"""First-run wizard endpoints. /api/setup/* is gate-exempt."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from curbcam.camera.discovery import discover_cameras
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
    # This endpoint is gate-exempt and unauthenticated so a fresh install can
    # bootstrap. It must therefore set the password ONLY when none exists —
    # otherwise it's an unauthenticated password-reset / account-takeover on a
    # configured device. Password changes go through authenticated Settings.
    if sup.auth.has_password():
        raise HTTPException(status_code=409, detail="Admin password already set")
    sup.auth.set_password(password)
    resp = templates.TemplateResponse(request, "setup/configure.html", {})
    issue_session(sup, resp)
    return resp


@router.post("/api/setup/login", response_class=HTMLResponse)
def setup_login(
    request: Request,
    password: str = Form(...),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    if not sup.auth.has_password():
        raise HTTPException(status_code=409, detail="Admin password is not set")
    if not sup.auth.verify_password(password):
        time.sleep(0.25)
        raise HTTPException(status_code=401, detail="Invalid password")
    resp = templates.TemplateResponse(request, "setup/configure.html", {})
    issue_session(sup, resp)
    return resp


@router.get("/api/setup/cameras", response_class=HTMLResponse)
async def setup_cameras(
    request: Request,
    _: None = Depends(require_session),
) -> HTMLResponse:
    # Discovery probes hardware (ioctls, picamera2) — run off the event loop.
    cameras = await run_in_threadpool(discover_cameras)
    return templates.TemplateResponse(request, "setup/cameras.html", {"cameras": cameras})


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
