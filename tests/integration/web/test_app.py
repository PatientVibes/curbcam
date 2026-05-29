from fastapi.testclient import TestClient


def test_debug_stats_returns_running_true(client: TestClient, supervisor) -> None:  # type: ignore[no-untyped-def]
    # /api/debug/stats is gated (not in the first-run exempt list, spec §6) AND
    # session-protected, so configure the app and log in before asserting stats.
    supervisor.auth.set_password("x")
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": "x"})
    resp = client.get("/api/debug/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["running"] is True
    assert "uptime_s" in body


def test_debug_stats_requires_session_when_configured(client: TestClient, supervisor) -> None:  # type: ignore[no-untyped-def]
    # Configured (gate does not redirect) but no session: the login cookie must
    # actually protect the endpoint — see spec §6 "per-route require_session".
    supervisor.auth.set_password("x")
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    resp = client.get("/api/debug/stats", follow_redirects=False)
    assert resp.status_code == 401
