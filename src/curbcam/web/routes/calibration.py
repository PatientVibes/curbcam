"""Calibration wizard endpoints (spec §8.7).

capture: freeze the current live frame as a JPEG for measurement. The
frontend reads the source resolution from the returned image's
naturalWidth/naturalHeight, so no separate dimensions payload is needed.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from curbcam.web.deps import get_supervisor, require_session
from curbcam.web.supervisor import Supervisor

router = APIRouter()


@router.post("/api/calibration/capture")
def capture(
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> Response:
    got = sup.capture_still()
    if got is None:
        raise HTTPException(status_code=503, detail="No frame available yet")
    jpeg, _w, _h = got
    return Response(content=jpeg, media_type="image/jpeg")
