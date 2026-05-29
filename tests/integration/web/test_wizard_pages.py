def _login(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    client.post("/api/auth/login", data={"password": password})


def test_calibrate_wizard_page_renders(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _login(client, supervisor)
    resp = client.get("/setup/calibrate")
    assert resp.status_code == 200
    assert 'id="capture"' in resp.text
    assert "calibrate.js" in resp.text


def test_align_wizard_page_renders(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _login(client, supervisor)
    resp = client.get("/setup/align")
    assert resp.status_code == 200
    assert 'id="align-canvas"' in resp.text
    assert "align.js" in resp.text
