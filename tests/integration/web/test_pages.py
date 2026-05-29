import datetime as dt


def _configure(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": password})


def test_dashboard_renders_with_stream_and_events(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    supervisor.events.save(
        ts_utc=dt.datetime(2026, 5, 28, 12, 0, 0),
        speed_kph=42.0,
        direction="L2R",
        frame_count=10,
        track_len_px=200,
        image_path="events/e.jpg",
        thumb_path="thumbs/e.jpg",
        calibration_id=None,
    )
    resp = client.get("/")
    assert resp.status_code == 200
    assert "/api/stream.mjpeg" in resp.text
    assert "/api/events/stream" in resp.text
    assert "42.0 kph" in resp.text


def test_media_requires_session_when_configured(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    # Event images are private (spec §6): configured but no session -> 401,
    # never served by a bare static mount.
    supervisor.auth.set_password("pw")
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    (supervisor.media_root / "events").mkdir(parents=True, exist_ok=True)
    (supervisor.media_root / "events" / "x.jpg").write_bytes(b"\xff\xd8jpeg")
    resp = client.get("/media/events/x.jpg", follow_redirects=False)
    assert resp.status_code == 401


def test_media_served_to_authenticated_admin(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    (supervisor.media_root / "events").mkdir(parents=True, exist_ok=True)
    (supervisor.media_root / "events" / "x.jpg").write_bytes(b"\xff\xd8jpeg")
    resp = client.get("/media/events/x.jpg")
    assert resp.status_code == 200
    assert resp.content == b"\xff\xd8jpeg"


def test_media_rejects_path_outside_root(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    # Plant a real file just OUTSIDE media_root; a percent-encoded traversal
    # that resolves to it must 404 (is_relative_to guard), not leak it.
    secret = supervisor.media_root.parent / "secret.txt"
    secret.write_text("private", encoding="utf-8")
    resp = client.get("/media/..%2fsecret.txt")
    assert resp.status_code == 404
    assert "private" not in resp.text
