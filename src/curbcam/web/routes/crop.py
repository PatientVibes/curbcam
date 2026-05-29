"""Alignment wizard: save the detection crop rectangle (spec §8.6).

Rect is in SOURCE-frame coordinates (the JS scales display->source). On
save: validate against the configured resolution, persist detector.crop,
graceful restart.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from curbcam.config.schema import Settings
from curbcam.web.deps import get_supervisor, require_session
from curbcam.web.supervisor import Supervisor

router = APIRouter()


class CropIn(BaseModel):
    x0: int
    y0: int
    x1: int
    y1: int


@router.post("/api/crop")
async def save_crop(
    body: CropIn,
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> Response:
    settings = sup.config_store.load()
    w, h = settings.camera.resolution
    if not (0 <= body.x0 < body.x1 <= w and 0 <= body.y0 < body.y1 <= h):
        raise HTTPException(status_code=422, detail="invalid crop rectangle")

    raw = sup.config_store.load_raw()
    raw.setdefault("detector", {})["crop"] = [body.x0, body.y0, body.x1, body.y1]
    Settings.model_validate(raw)  # defense in depth
    sup.config_store.save_raw(raw)
    await run_in_threadpool(sup.restart)
    return Response(status_code=204)
