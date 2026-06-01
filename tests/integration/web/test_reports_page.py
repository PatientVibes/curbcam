import datetime as dt


def _configure(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": password})


def _seed(supervisor, n: int = 5) -> None:  # type: ignore[no-untyped-def]
    for i in range(n):
        supervisor.events.save(
            ts_utc=dt.datetime.now() - dt.timedelta(hours=i),
            speed_kph=30.0 + i,
            direction="L2R" if i % 2 else "R2L",
            frame_count=10,
            track_len_px=200,
            image_path=f"e_{i}.jpg",
            thumb_path=f"t_{i}.jpg",
            calibration_id=None,
        )


def test_reports_requires_session(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password("pw")
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    resp = client.get("/reports", follow_redirects=False)
    assert resp.status_code == 401


def test_reports_page_renders_with_data(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    _seed(supervisor)
    resp = client.get("/reports")
    assert resp.status_code == 200
    assert "Reports" in resp.text
    assert "<svg" in resp.text  # inline-SVG charts present


def test_reports_partial_window_switch(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    _seed(supervisor)
    resp = client.get("/api/reports?window=30d")
    assert resp.status_code == 200
    assert "<svg" in resp.text


def test_reports_empty_state(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    resp = client.get("/reports")
    assert resp.status_code == 200
    assert "No events" in resp.text


def test_reports_nav_link_present(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    resp = client.get("/")
    assert 'href="/reports"' in resp.text
