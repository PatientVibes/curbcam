"""Detector stats for the dashboard pill + diagnostics."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from curbcam.web.deps import get_supervisor, require_session
from curbcam.web.supervisor import Supervisor

router = APIRouter()


@router.get("/api/debug/stats")
def debug_stats(
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> dict[str, object]:
    return sup.stats()
