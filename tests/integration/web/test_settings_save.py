def _configure(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": password})


def _form(supervisor, **overrides) -> dict:  # type: ignore[no-untyped-def]
    raw = supervisor.config_store.load_raw()
    data = {
        "camera.source": overrides.get("source", raw["camera"]["source"]),
        "camera.resolution": overrides.get("resolution", "1280x720"),
        "camera.fps_target": overrides.get("fps_target", "15"),
        "server.units": overrides.get("units", "kph"),
        "server.min_event_speed_kph": overrides.get("min_event_speed_kph", "5"),
        "detector.min_area_px": "800",
        "detector.min_track_frames": "5",
        "detector.max_dist_px": "100",
        "retention.max_events_per_day": "500",
        "retention.max_total_disk_mb": "5000",
        "server.log_level": "INFO",
    }
    return data


def test_valid_save_persists_and_restarts(client, supervisor, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    restarts: list[int] = []
    monkeypatch.setattr(supervisor, "restart", lambda: restarts.append(1))
    resp = client.post("/api/settings", data=_form(supervisor, units="mph"))
    assert resp.status_code == 200
    assert supervisor.config_store.load_raw()["server"]["units"] == "mph"
    assert restarts == [1]


def test_invalid_value_returns_422_with_inline_error(client, supervisor, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    monkeypatch.setattr(supervisor, "restart", lambda: None)
    resp = client.post("/api/settings", data=_form(supervisor, fps_target="-3"))
    assert resp.status_code == 422
    assert "field-error" in resp.text
    # Bad value was NOT persisted.
    assert float(supervisor.config_store.load_raw()["camera"]["fps_target"]) > 0


def test_malformed_resolution_returns_422_and_is_not_persisted(
    client, supervisor, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    # A malformed resolution must surface a validation error, not be silently
    # dropped while reporting a successful save.
    _configure(client, supervisor)
    monkeypatch.setattr(supervisor, "restart", lambda: None)
    resp = client.post("/api/settings", data=_form(supervisor, resolution="abc"))
    assert resp.status_code == 422
    assert "field-error" in resp.text
    assert supervisor.config_store.load_raw()["camera"]["resolution"] == [1280, 720]
