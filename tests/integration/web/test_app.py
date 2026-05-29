from fastapi.testclient import TestClient


def test_debug_stats_returns_running_true(client: TestClient) -> None:
    resp = client.get("/api/debug/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["running"] is True
    assert "uptime_s" in body
