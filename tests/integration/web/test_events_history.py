import datetime as dt


def _configure(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": password})


def _seed(supervisor, n: int = 5) -> None:  # type: ignore[no-untyped-def]
    for i in range(n):
        supervisor.events.save(
            ts_utc=dt.datetime(2026, 5, 28, 12, i, 0),
            speed_kph=20.0 + i * 10,
            direction="L2R" if i % 2 == 0 else "R2L",
            frame_count=10, track_len_px=200,
            image_path=f"events/e_{i}.jpg", thumb_path=f"thumbs/e_{i}.jpg",
            calibration_id=None,
        )


def test_events_page_renders_filter_form(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    resp = client.get("/events")
    assert resp.status_code == 200
    assert 'name="direction"' in resp.text


def test_api_events_filters_by_direction(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    _seed(supervisor)
    resp = client.get("/api/events", params={"direction": "R2L"})
    assert resp.status_code == 200
    # 2 R2L events (indices 1,3); cards carry data-event-id.
    assert resp.text.count("data-event-id") == 2


def test_api_events_requires_auth(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("pw")
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    resp = client.get("/api/events", follow_redirects=False)
    assert resp.status_code == 401
