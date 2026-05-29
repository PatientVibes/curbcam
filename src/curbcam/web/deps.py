"""FastAPI dependencies. Auth deps are filled in Slice B."""
from __future__ import annotations

from fastapi import Request

from curbcam.web.supervisor import Supervisor


def get_supervisor(request: Request) -> Supervisor:
    return request.app.state.supervisor  # type: ignore[no-any-return]
