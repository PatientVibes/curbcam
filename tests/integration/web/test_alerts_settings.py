def _configure(client, supervisor, password: str = "pw") -> None:  # type: ignore[no-untyped-def]
    supervisor.auth.set_password(password)
    supervisor.calibrations.save_new_active(40.0, 40.0, 4000.0, "[]")
    client.post("/api/auth/login", data={"password": password})


def _full_form(overrides: dict[str, str]) -> dict[str, str]:
    # The settings POST overlays submitted keys; send the alert fields the form
    # renders so a save reflects exactly the on-screen state.
    base = {
        "camera.source": "file:./x",
        "camera.resolution": "640x480",
        "camera.fps_target": "15",
        "server.units": "kph",
        "server.min_event_speed_kph": "5",
        "detector.min_area_px": "800",
        "detector.min_track_frames": "5",
        "detector.max_dist_px": "100",
        "retention.max_events_per_day": "500",
        "retention.max_total_disk_mb": "5000",
        "server.log_level": "INFO",
        "alerts.enabled": "false",
        "alerts.min_speed_kph": "0",
        "alerts.base_url": "http://curbcam.local:8080",
        "alerts.ntfy_enabled": "false",
        "alerts.ntfy_server": "https://ntfy.sh",
        "alerts.ntfy_topic": "",
        "alerts.ntfy_cooldown_s": "60",
        "alerts.webhook_enabled": "false",
        "alerts.webhook_url": "",
        "alerts.webhook_cooldown_s": "60",
        "alerts.mqtt_enabled": "false",
        "alerts.mqtt_host": "",
        "alerts.mqtt_port": "1883",
        "alerts.mqtt_topic": "curbcam/events",
        "alerts.mqtt_username": "",
        "alerts.mqtt_password": "",
        "alerts.mqtt_cooldown_s": "0",
    }
    base.update(overrides)
    return base


def test_settings_page_renders_alerts_group(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert 'name="alerts.enabled"' in resp.text
    assert "Alerts" in resp.text  # fieldset legend (group name capitalized)


def test_alert_boolean_can_be_toggled_off(client, supervisor) -> None:  # type: ignore[no-untyped-def]
    _configure(client, supervisor)
    # Enable, then disable, and assert the on-disk YAML reflects the OFF state.
    client.post("/api/settings", data=_full_form({"alerts.enabled": "true"}))
    assert supervisor.config_store.load().alerts.enabled is True
    client.post("/api/settings", data=_full_form({"alerts.enabled": "false"}))
    assert supervisor.config_store.load().alerts.enabled is False
    raw = supervisor.config_store.load_raw()
    assert raw["alerts"]["enabled"] is False  # real bool, not the string "true"
