"""Calibration wizard endpoints (spec §8.7).

capture: freeze the current live frame as a JPEG for measurement. The
frontend reads the source resolution from the returned image's
naturalWidth/naturalHeight, so no separate dimensions payload is needed.
"""

from __future__ import annotations

import json
import math

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, field_validator

from curbcam.web.deps import get_supervisor, require_session
from curbcam.web.supervisor import Supervisor
from curbcam.web.units import distance_to_mm

router = APIRouter()


class MeasureIn(BaseModel):
    points: list[tuple[float, float]]
    distance: float
    units: str
    direction: str

    @field_validator("points")
    @classmethod
    def _exactly_two(cls, v: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(v) != 2:
            raise ValueError("exactly two points required")
        return v

    @field_validator("direction")
    @classmethod
    def _dir(cls, v: str) -> str:
        if v not in ("L2R", "R2L"):
            raise ValueError("direction must be L2R or R2L")
        return v


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


@router.post("/api/calibration/measure")
def measure(
    body: MeasureIn,
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> dict[str, object]:
    settings = sup.config_store.load()
    w, h = settings.camera.resolution
    for x, y in body.points:
        if not (0 <= x <= w and 0 <= y <= h):
            raise HTTPException(status_code=422, detail="point out of frame bounds")

    (x0, y0), (x1, y1) = body.points
    pixel_distance = math.hypot(x1 - x0, y1 - y0)
    if pixel_distance <= 0:
        raise HTTPException(status_code=422, detail="points must differ")
    try:
        distance_mm = distance_to_mm(body.distance, body.units)
    except KeyError:
        raise HTTPException(status_code=422, detail="unknown distance unit") from None
    if distance_mm <= 0:
        raise HTTPException(status_code=422, detail="distance must be positive")

    mm_per_px = round(distance_mm / pixel_distance, 6)

    active = sup.calibrations.get_active()
    l2r = float(active.mm_per_px_l2r) if active else None
    r2l = float(active.mm_per_px_r2l) if active else None
    if body.direction == "L2R":
        l2r = mm_per_px
        r2l = r2l if r2l is not None else mm_per_px
    else:
        r2l = mm_per_px
        l2r = l2r if l2r is not None else mm_per_px

    cal = sup.calibrations.save_new_active(
        mm_per_px_l2r=l2r,
        mm_per_px_r2l=r2l,
        reference_distance_mm=distance_mm,
        reference_points_json=json.dumps(body.points),
    )
    return {"mm_per_px": mm_per_px, "direction": body.direction, "calibration_id": cal.id}
