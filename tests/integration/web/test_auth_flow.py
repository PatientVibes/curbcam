from fastapi.testclient import TestClient


def test_login_rejects_bad_password(client: TestClient, supervisor) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("correct-horse")
    resp = client.post("/api/auth/login", data={"password": "nope"}, follow_redirects=False)
    assert resp.status_code == 401


def test_login_sets_session_cookie(client: TestClient, supervisor) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("correct-horse")
    resp = client.post(
        "/api/auth/login", data={"password": "correct-horse"}, follow_redirects=False
    )
    assert resp.status_code in (200, 303)
    assert "curbcam_session" in resp.cookies


def test_logout_clears_session(client: TestClient, supervisor) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("correct-horse")
    # /api/auth/logout is gated (only /api/auth/login is exempt, spec §6), so
    # an active calibration is needed for the app to be past the first-run gate.
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": "correct-horse"})
    resp = client.delete("/api/auth/logout")
    assert resp.status_code in (200, 204)
