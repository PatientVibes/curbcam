"""/healthz must answer 200 even on a brand-new, unconfigured install —
the first-run gate must NOT redirect it (the Docker HEALTHCHECK + CI smoke
test depend on this)."""
from fastapi.testclient import TestClient


def test_healthz_ok_on_unconfigured_app(client: TestClient) -> None:
    # The `client` fixture (tests/integration/web/conftest.py) builds an app
    # with no password and no calibration -> the gate is active.
    resp = client.get("/healthz", follow_redirects=False)
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_root_still_redirects_when_unconfigured(client: TestClient) -> None:
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/setup"
