import datetime as dt


def _configure(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": password})


def test_dashboard_renders_with_stream_and_events(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    supervisor.events.save(
        ts_utc=dt.datetime(2026, 5, 28, 12, 0, 0),
        speed_kph=42.0, direction="L2R", frame_count=10, track_len_px=200,
        image_path="events/e.jpg", thumb_path="thumbs/e.jpg", calibration_id=None,
    )
    resp = client.get("/")
    assert resp.status_code == 200
    assert "/api/stream.mjpeg" in resp.text
    assert "/api/events/stream" in resp.text
    assert "42.0 kph" in resp.text
