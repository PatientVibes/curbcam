from fastapi.testclient import TestClient


def test_debug_stats_returns_running_true(client: TestClient, supervisor) -> None:  # type: ignore[no-untyped-def]
    # /api/debug/stats is gated (not in the first-run exempt list, spec §6),
    # so configure the app before asserting the live stats it returns.
    supervisor.auth.set_password("x")
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    resp = client.get("/api/debug/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["running"] is True
    assert "uptime_s" in body
