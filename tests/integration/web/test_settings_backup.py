"""Settings export / import.

Two properties matter most here: a round trip must actually restore the values
(a backup that silently loses settings is worse than none), and an import must
reject junk rather than writing an unusable config and restarting the detector
into a broken state.
"""

from __future__ import annotations

import yaml
from fastapi.testclient import TestClient

from curbcam.web.supervisor import Supervisor


def _login(client: TestClient, sup: Supervisor) -> None:
    sup.auth.set_password("x")
    sup.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": "x"})


def test_export_returns_a_yaml_attachment(client: TestClient, supervisor: Supervisor) -> None:
    _login(client, supervisor)
    r = client.get("/api/settings/export")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    assert ".yaml" in r.headers["content-disposition"]
    parsed = yaml.safe_load(r.text)
    assert isinstance(parsed, dict)
    assert "camera" in parsed


def test_export_documents_what_it_omits(client: TestClient, supervisor: Supervisor) -> None:
    """The file is handed to humans, so it must say what is NOT in it -- someone
    restoring after a failure should not assume their calibration came back."""
    _login(client, supervisor)
    body = client.get("/api/settings/export").text
    assert "calibration" in body.lower()
    assert "credential" in body.lower() or "password" in body.lower()


def test_export_excludes_secrets(client: TestClient, supervisor: Supervisor) -> None:
    """Password hashes and stream tokens live in auth.json and must never end up
    in a file people email around or paste into an issue."""
    _login(client, supervisor)
    supervisor.auth.mint_stream_token("home assistant")
    body = client.get("/api/settings/export").text
    parsed = yaml.safe_load(body)
    assert "auth" not in parsed
    assert "tokens" not in parsed
    assert "password_hash" not in body


def test_round_trip_restores_values(client: TestClient, supervisor: Supervisor) -> None:
    _login(client, supervisor)

    raw = supervisor.config_store.load_raw()
    raw.setdefault("server", {})["units"] = "mph"
    raw.setdefault("retention", {})["max_events_per_day"] = 123
    supervisor.config_store.save_raw(raw)

    exported = client.get("/api/settings/export").text

    # Drift away from the exported state...
    raw = supervisor.config_store.load_raw()
    raw["server"]["units"] = "kph"
    raw["retention"]["max_events_per_day"] = 500
    supervisor.config_store.save_raw(raw)

    r = client.post(
        "/api/settings/import",
        files={"file": ("curbcam-settings.yaml", exported, "application/x-yaml")},
    )
    assert "test-ok" in r.text

    restored = supervisor.config_store.load_raw()
    assert restored["server"]["units"] == "mph"
    assert restored["retention"]["max_events_per_day"] == 123


def test_import_rejects_invalid_yaml(client: TestClient, supervisor: Supervisor) -> None:
    _login(client, supervisor)
    before = supervisor.config_store.load_raw()
    r = client.post(
        "/api/settings/import",
        files={"file": ("bad.yaml", b"server: [unclosed\n  bracket: :", "application/x-yaml")},
    )
    assert "test-fail" in r.text
    assert supervisor.config_store.load_raw() == before, "config must be untouched on failure"


def test_import_rejects_values_that_fail_validation(
    client: TestClient, supervisor: Supervisor
) -> None:
    """Structurally valid YAML with a nonsense value must not be written -- it
    would restart the detector into a config it cannot load."""
    _login(client, supervisor)
    before = supervisor.config_store.load_raw()
    bad = yaml.safe_dump({"server": {"units": "furlongs-per-fortnight"}})
    r = client.post(
        "/api/settings/import",
        files={"file": ("bad.yaml", bad, "application/x-yaml")},
    )
    assert "test-fail" in r.text
    # The message should name the offending field, not just say "invalid".
    assert "units" in r.text
    assert supervisor.config_store.load_raw() == before


def test_import_rejects_a_non_mapping(client: TestClient, supervisor: Supervisor) -> None:
    _login(client, supervisor)
    r = client.post(
        "/api/settings/import",
        files={"file": ("bad.yaml", b"- just\n- a\n- list\n", "application/x-yaml")},
    )
    assert "test-fail" in r.text


def test_import_rejects_an_empty_file(client: TestClient, supervisor: Supervisor) -> None:
    _login(client, supervisor)
    r = client.post(
        "/api/settings/import",
        files={"file": ("empty.yaml", b"   \n", "application/x-yaml")},
    )
    assert "test-fail" in r.text


def test_import_requires_a_session_once_configured(
    client: TestClient, supervisor: Supervisor
) -> None:
    """Import replaces the whole config and restarts the detector -- it must not
    be reachable without a session."""
    supervisor.auth.set_password("x")
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    r = client.post(
        "/api/settings/import",
        files={"file": ("x.yaml", b"server: {}\n", "application/x-yaml")},
        follow_redirects=False,
    )
    assert r.status_code == 401
