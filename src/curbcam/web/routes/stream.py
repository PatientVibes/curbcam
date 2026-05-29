"""Live MJPEG preview. Accepts a session cookie OR a ?token= stream token."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from curbcam.web.deps import get_supervisor, require_stream_auth
from curbcam.web.streams import mjpeg_generator
from curbcam.web.supervisor import Supervisor

router = APIRouter()


@router.get("/api/stream.mjpeg")
def stream_mjpeg(
    _: None = Depends(require_stream_auth),
    sup: Supervisor = Depends(get_supervisor),
) -> StreamingResponse:
    resp = StreamingResponse(
        mjpeg_generator(sup),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return resp
