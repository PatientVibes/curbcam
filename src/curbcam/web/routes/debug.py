"""Detector stats for the dashboard pill + diagnostics."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from curbcam.web.deps import get_supervisor
from curbcam.web.supervisor import Supervisor

router = APIRouter()


@router.get("/api/debug/stats")
def debug_stats(sup: Supervisor = Depends(get_supervisor)) -> dict:
    return sup.stats()
