from fastapi.testclient import TestClient


def test_unconfigured_redirects_to_setup(client: TestClient) -> None:
    # No password set + no active calibration → gate redirects.
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/setup"


def test_setup_and_static_are_exempt(client: TestClient) -> None:
    resp = client.get("/setup", follow_redirects=False)
    assert resp.status_code != 303  # may 200 or 404 (page added later), never redirected


def test_login_endpoint_is_exempt(client: TestClient) -> None:
    resp = client.post("/api/auth/login", data={"password": "x"}, follow_redirects=False)
    # Not redirected by the gate; auth route handles it (401 here, no password yet).
    assert resp.status_code == 401


def test_configured_does_not_redirect(client: TestClient, supervisor) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("x")
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    # Authenticated session present:
    client.post("/api/auth/login", data={"password": "x"})
    resp = client.get("/api/debug/stats", follow_redirects=False)
    assert resp.status_code == 200
