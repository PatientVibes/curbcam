def _login(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    client.post("/api/auth/login", data={"password": password})


def test_crop_saves_and_restarts(client, supervisor, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _login(client, supervisor)
    restarts: list[int] = []
    monkeypatch.setattr(supervisor, "restart", lambda: restarts.append(1))
    resp = client.post("/api/crop", json={"x0": 100, "y0": 50, "x1": 500, "y1": 400})
    assert resp.status_code in (200, 204)
    assert supervisor.config_store.load_raw()["detector"]["crop"] == [100, 50, 500, 400]
    assert restarts == [1]


def test_crop_rejects_inverted_rect(client, supervisor, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _login(client, supervisor)
    monkeypatch.setattr(supervisor, "restart", lambda: None)
    resp = client.post("/api/crop", json={"x0": 500, "y0": 400, "x1": 100, "y1": 50})
    assert resp.status_code == 422


def test_crop_rejects_out_of_bounds(client, supervisor, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _login(client, supervisor)
    monkeypatch.setattr(supervisor, "restart", lambda: None)
    resp = client.post("/api/crop", json={"x0": 0, "y0": 0, "x1": 99999, "y1": 400})
    assert resp.status_code == 422
