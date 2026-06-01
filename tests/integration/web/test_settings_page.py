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


def test_settings_camera_source_offers_autodetect_datalist(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    resp = client.get("/settings")
    assert 'list="camera-source-options"' in resp.text  # text input keeps free-form entry
    assert 'id="camera-source-options"' in resp.text  # datalist that hx-loads cameras
    assert 'hx-get="/api/cameras"' in resp.text


def test_settings_camera_datalist_omitted_when_env_shadowed(
    client, supervisor, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    monkeypatch.setenv("CURBCAM_CAMERA__SOURCE", "rtsp://env-host/s")
    resp = client.get("/settings")
    assert 'hx-get="/api/cameras"' not in resp.text  # read-only: nothing to detect into


def test_cameras_endpoint_requires_session(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    # Fully configured so the first-run gate doesn't redirect, but no login —
    # require_session must reject.
    supervisor.auth.set_password("pw")
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    resp = client.get("/api/cameras", follow_redirects=False)
    assert resp.status_code == 401


def test_cameras_endpoint_renders_discovered_options(client, supervisor, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from curbcam.camera.discovery import DiscoveredCamera

    _configure(client, supervisor)
    monkeypatch.setattr(
        "curbcam.web.routes.settings.discover_cameras",
        lambda: [DiscoveredCamera("picamera2:0", "Pi Camera 0 — imx219", "picamera2")],
    )
    resp = client.get("/api/cameras")
    assert resp.status_code == 200
    assert '<option value="picamera2:0">Pi Camera 0 — imx219</option>' in resp.text
