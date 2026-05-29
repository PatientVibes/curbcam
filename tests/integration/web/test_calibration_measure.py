def _login(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    client.post("/api/auth/login", data={"password": password})


def test_measure_computes_mm_per_px_l2r(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _login(client, supervisor)
    # 100 px apart, 5 m real distance -> 5000 mm / 100 px = 50 mm/px.
    body = {
        "points": [[100, 100], [200, 100]],
        "distance": 5.0, "units": "m", "direction": "L2R",
    }
    resp = client.post("/api/calibration/measure", json=body)
    assert resp.status_code == 200
    assert resp.json()["mm_per_px"] == 50.0
    active = supervisor.calibrations.get_active()
    assert active is not None
    assert float(active.mm_per_px_l2r) == 50.0
    # R2L defaults to the same until separately calibrated.
    assert float(active.mm_per_px_r2l) == 50.0


def test_measure_rejects_out_of_bounds_points(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _login(client, supervisor)
    # Default resolution is 1280x720; y=9999 is out of bounds.
    body = {
        "points": [[10, 10], [20, 9999]],
        "distance": 1.0, "units": "m", "direction": "L2R",
    }
    resp = client.post("/api/calibration/measure", json=body)
    assert resp.status_code == 422


def test_measure_second_direction_preserves_first(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _login(client, supervisor)
    client.post("/api/calibration/measure", json={
        "points": [[100, 100], [200, 100]], "distance": 5.0, "units": "m", "direction": "L2R",
    })
    client.post("/api/calibration/measure", json={
        "points": [[100, 100], [300, 100]], "distance": 5.0, "units": "m", "direction": "R2L",
    })
    active = supervisor.calibrations.get_active()
    assert float(active.mm_per_px_l2r) == 50.0      # preserved
    assert float(active.mm_per_px_r2l) == 25.0      # 5000 / 200
