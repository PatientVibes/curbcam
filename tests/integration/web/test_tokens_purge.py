import datetime as dt


def _configure(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": password})


def test_mint_then_revoke_token(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    resp = client.post("/api/tokens", data={"label": "Home Assistant"})
    assert resp.status_code == 200
    assert "Home Assistant" in resp.text
    tokens = supervisor.auth.list_stream_tokens()
    assert len(tokens) == 1
    tid = tokens[0]["id"]
    resp = client.delete(f"/api/tokens/{tid}")
    assert resp.status_code == 200
    assert supervisor.auth.list_stream_tokens() == []


def test_purge_old_events(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    old = dt.datetime(2020, 1, 1, 0, 0, 0)
    supervisor.events.save(
        ts_utc=old,
        speed_kph=30.0,
        direction="L2R",
        frame_count=10,
        track_len_px=100,
        image_path="events/o.jpg",
        thumb_path="thumbs/o.jpg",
        calibration_id=None,
    )
    resp = client.post("/api/events/purge", data={"days": "30"})
    assert resp.status_code in (200, 204)
    from curbcam.storage.repositories import EventFilter

    assert supervisor.events.query(EventFilter()) == []


def test_purge_rejects_nonpositive_days(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    # days<=0 would push the cutoff to now/future and wipe ALL events; the
    # server must reject it (the form's min=1 is only client-side).
    _configure(client, supervisor)
    supervisor.events.save(
        ts_utc=dt.datetime(2020, 1, 1, 0, 0, 0),
        speed_kph=30.0,
        direction="L2R",
        frame_count=10,
        track_len_px=100,
        image_path="events/o.jpg",
        thumb_path="thumbs/o.jpg",
        calibration_id=None,
    )
    resp = client.post("/api/events/purge", data={"days": "0"})
    assert resp.status_code == 422
    from curbcam.storage.repositories import EventFilter

    assert len(supervisor.events.query(EventFilter())) == 1  # nothing deleted
