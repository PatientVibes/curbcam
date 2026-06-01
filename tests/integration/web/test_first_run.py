def test_setup_shows_password_form_when_unconfigured(client) -> None:  # type: ignore[no-untyped-def]
    resp = client.get("/setup")
    assert resp.status_code == 200
    assert 'name="password"' in resp.text


def test_setup_password_sets_password_and_session(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    resp = client.post("/api/setup/password", data={"password": "s3cret"})
    assert resp.status_code == 200
    assert supervisor.auth.has_password() is True
    assert "curbcam_session" in resp.cookies
    assert 'id="camera-picker"' in resp.text  # configure panel follows


def test_setup_password_rejected_once_set(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    # /api/setup/password is unauthenticated for bootstrap; once a password
    # exists it must refuse, or it's an unauthenticated account-takeover.
    supervisor.auth.set_password("original")
    resp = client.post("/api/setup/password", data={"password": "attacker"}, follow_redirects=False)
    assert resp.status_code == 409
    assert supervisor.auth.verify_password("original") is True
    assert supervisor.auth.verify_password("attacker") is False


def test_setup_shows_login_form_when_password_exists_without_session(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("s3cret")
    resp = client.get("/setup")
    assert resp.status_code == 200
    assert "Admin login required" in resp.text
    assert 'hx-post="/api/setup/login"' in resp.text


def test_setup_login_sets_session_and_returns_configure(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("s3cret")
    resp = client.post("/api/setup/login", data={"password": "s3cret"})
    assert resp.status_code == 200
    assert "curbcam_session" in resp.cookies
    assert 'id="camera-picker"' in resp.text


def test_setup_cameras_requires_session(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("s3cret")
    resp = client.get("/api/setup/cameras")
    assert resp.status_code == 401


def test_setup_cameras_renders_discovered_options(client, supervisor, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from curbcam.camera.discovery import DiscoveredCamera

    supervisor.auth.set_password("s3cret")
    client.post("/api/auth/login", data={"password": "s3cret"})
    monkeypatch.setattr(
        "curbcam.web.routes.setup.discover_cameras",
        lambda: [DiscoveredCamera("picamera2:0", "Pi Camera 0 — imx708", "picamera2")],
    )
    resp = client.get("/api/setup/cameras")
    assert resp.status_code == 200
    assert 'value="picamera2:0"' in resp.text
    assert "Pi Camera 0 — imx708" in resp.text
    assert 'hx-post="/api/setup/camera"' in resp.text


def test_setup_cameras_empty_falls_back_to_manual_entry(client, supervisor, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("s3cret")
    client.post("/api/auth/login", data={"password": "s3cret"})
    monkeypatch.setattr("curbcam.web.routes.setup.discover_cameras", list)
    resp = client.get("/api/setup/cameras")
    assert resp.status_code == 200
    assert 'name="source"' in resp.text  # manual input still available


def test_setup_camera_saves_source_and_restarts(client, supervisor, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("s3cret")
    client.post("/api/auth/login", data={"password": "s3cret"})
    restarts: list[int] = []
    monkeypatch.setattr(supervisor, "restart", lambda: restarts.append(1))
    resp = client.post("/api/setup/camera", data={"source": "usb:0"})
    assert resp.status_code == 200
    assert supervisor.config_store.load_raw()["camera"]["source"] == "usb:0"
    assert restarts == [1]


def test_setup_redirects_home_when_fully_configured(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("s3cret")
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": "s3cret"})
    resp = client.get("/setup", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
