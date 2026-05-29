def _configure(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": password})


def test_settings_page_shows_fields(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert 'name="camera.source"' in resp.text
    assert 'name="detector.min_area_px"' in resp.text


def test_env_shadowed_field_is_readonly(client, supervisor, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    monkeypatch.setenv("CURBCAM_CAMERA__SOURCE", "rtsp://env-host/s")
    resp = client.get("/settings")
    assert "set via environment" in resp.text
