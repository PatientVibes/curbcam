from fastapi.testclient import TestClient


def test_login_rejects_bad_password(client: TestClient, supervisor) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("correct-horse")
    resp = client.post("/api/auth/login", data={"password": "nope"}, follow_redirects=False)
    assert resp.status_code == 401


def test_login_sets_session_cookie(client: TestClient, supervisor) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("correct-horse")
    resp = client.post("/api/auth/login", data={"password": "correct-horse"}, follow_redirects=False)
    assert resp.status_code in (200, 303)
    assert "curbcam_session" in resp.cookies


def test_logout_clears_session(client: TestClient, supervisor) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("correct-horse")
    client.post("/api/auth/login", data={"password": "correct-horse"})
    resp = client.delete("/api/auth/logout")
    assert resp.status_code in (200, 204)
