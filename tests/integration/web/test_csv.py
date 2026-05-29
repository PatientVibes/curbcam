import datetime as dt


def _configure(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": password})


def test_csv_export_headers_and_unit_conversion(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    # Switch display units to mph so we can assert conversion.
    s = supervisor.config_store.load()
    s = s.model_copy(update={"server": s.server.model_copy(update={"units": "mph"})})
    supervisor.config_store.save(s)
    _configure(client, supervisor)
    supervisor.events.save(
        ts_utc=dt.datetime(2026, 5, 28, 12, 0, 0),
        speed_kph=80.4672,
        direction="L2R",
        frame_count=10,
        track_len_px=200,
        image_path="events/e.jpg",
        thumb_path="thumbs/e.jpg",
        calibration_id=None,
    )
    resp = client.get("/api/events.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers.get("content-disposition", "")
    lines = resp.text.strip().splitlines()
    assert lines[0] == "id,ts_utc,speed,units,direction,frame_count,track_len_px,image_path"
    # 80.4672 kph == 50.0 mph
    assert ",50.0,mph," in lines[1]
