"""FastAPI dependencies + session cookie helpers."""

from __future__ import annotations

from fastapi import HTTPException, Query, Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer

from curbcam.web.supervisor import Supervisor

SESSION_COOKIE = "curbcam_session"
_MAX_AGE_S = 30 * 24 * 3600  # 30-day sliding expiry


def get_supervisor(request: Request) -> Supervisor:
    return request.app.state.supervisor  # type: ignore[no-any-return]


def _serializer(sup: Supervisor) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(sup.auth.secret_key(), salt="curbcam-session")


def issue_session(sup: Supervisor, response: Response) -> None:
    token = _serializer(sup).dumps({"admin": True})
    response.set_cookie(SESSION_COOKIE, token, max_age=_MAX_AGE_S, httponly=True, samesite="lax")


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)


def session_is_valid(sup: Supervisor, request: Request) -> bool:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return False
    try:
        _serializer(sup).loads(raw, max_age=_MAX_AGE_S)
        return True
    except BadSignature:
        return False


def require_session(request: Request) -> None:
    sup: Supervisor = request.app.state.supervisor
    if not session_is_valid(sup, request):
        raise HTTPException(status_code=401, detail="Not authenticated")


def require_stream_auth(request: Request, token: str | None = Query(default=None)) -> None:
    sup: Supervisor = request.app.state.supervisor
    if session_is_valid(sup, request):
        return
    if token and sup.auth.verify_stream_token(token):
        return
    raise HTTPException(status_code=401, detail="Not authenticated")
