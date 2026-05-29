"""Event feed (SSE) + history/CSV (history + CSV added in Slice D)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from curbcam.web.deps import get_supervisor, require_session
from curbcam.web.streams import sse_generator
from curbcam.web.supervisor import Supervisor

router = APIRouter()


@router.get("/api/events/stream")
def events_stream(
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> StreamingResponse:
    return StreamingResponse(sse_generator(sup), media_type="text/event-stream")
