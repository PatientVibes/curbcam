"""First-run gate (spec §6).

If no admin password OR no active calibration exists, every route except
the setup/auth/calibration/crop/static surface is 303-redirected to
/setup. The gate only controls redirection; per-route require_session
still enforces authentication on protected endpoints.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

_EXEMPT_PREFIXES = (
    "/setup",
    "/api/auth/login",
    "/api/calibration",
    "/api/crop",
    "/static",
)


def _is_exempt(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") or path.startswith(p) for p in _EXEMPT_PREFIXES)


async def first_run_gate(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    sup = request.app.state.supervisor
    if not _is_exempt(request.url.path):
        configured = sup.auth.has_password() and sup.calibrations.get_active() is not None
        if not configured:
            return RedirectResponse("/setup", status_code=303)
    return await call_next(request)
