"""Login/logout. /api/auth/login is the only fully public endpoint."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Form, HTTPException, Response

from curbcam.web.deps import clear_session, get_supervisor, issue_session
from curbcam.web.supervisor import Supervisor

router = APIRouter()


@router.post("/api/auth/login")
def login(
    password: str = Form(...),
    sup: Supervisor = Depends(get_supervisor),
) -> Response:
    if not sup.auth.verify_password(password):
        time.sleep(0.25)  # fixed delay blunts brute force (spec §6 threat model)
        raise HTTPException(status_code=401, detail="Invalid password")
    resp = Response(status_code=200)
    issue_session(sup, resp)
    return resp


@router.delete("/api/auth/logout")
def logout() -> Response:
    resp = Response(status_code=204)
    clear_session(resp)
    return resp
