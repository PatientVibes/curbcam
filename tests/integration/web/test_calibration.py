import time


def _login(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    client.post("/api/auth/login", data={"password": password})


def test_capture_returns_jpeg(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _login(client, supervisor)
    # The pipeline thread needs a moment to read the first frame.
    deadline = time.monotonic() + 3.0
    resp = client.post("/api/calibration/capture")
    while resp.status_code == 503 and time.monotonic() < deadline:
        resp = client.post("/api/calibration/capture")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content[:2] == b"\xff\xd8"
