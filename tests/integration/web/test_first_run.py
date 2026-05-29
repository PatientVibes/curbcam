def test_setup_shows_password_form_when_unconfigured(client) -> None:  # type: ignore[no-untyped-def]
    resp = client.get("/setup")
    assert resp.status_code == 200
    assert 'name="password"' in resp.text


def test_setup_password_sets_password_and_session(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    resp = client.post("/api/setup/password", data={"password": "s3cret"})
    assert resp.status_code == 200
    assert supervisor.auth.has_password() is True
    assert "curbcam_session" in resp.cookies
    assert 'name="source"' in resp.text  # configure panel follows


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
