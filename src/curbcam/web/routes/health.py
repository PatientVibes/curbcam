"""Liveness endpoint for Docker HEALTHCHECK + CI smoke (spec §4).

Unauthenticated and first-run-gate-exempt by design — it must answer before
any setup is done. Reports process liveness only; it does not probe the
camera/pipeline (a detector crash is handled by container restart, §4.3).
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
