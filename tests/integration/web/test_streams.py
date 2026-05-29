def test_mjpeg_requires_auth(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    # Configured (so the first-run gate does not redirect), but no session.
    supervisor.auth.set_password("x")
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    resp = client.get("/api/stream.mjpeg", follow_redirects=False)
    assert resp.status_code == 401
