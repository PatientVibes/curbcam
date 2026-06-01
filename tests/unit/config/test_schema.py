import pytest

from curbcam.config.defaults import FIELD_LABELS
from curbcam.config.schema import (
    DetectorSettings,
    RetentionSettings,
    ServerSettings,
    Settings,
)


def test_settings_round_trip_via_model_dump() -> None:
    s = Settings()
    dumped = s.model_dump()
    restored = Settings.model_validate(dumped)
    assert restored == s


def test_camera_source_defaults_to_picamera2() -> None:
    s = Settings()
    assert s.camera.source == "picamera2:0"


def test_units_must_be_kph_or_mph() -> None:
    with pytest.raises(ValueError):
        ServerSettings(units="mps")  # type: ignore[arg-type]


def test_detector_crop_is_optional() -> None:
    s = DetectorSettings()
    assert s.crop is None


def test_retention_caps_must_be_positive() -> None:
    with pytest.raises(ValueError):
        RetentionSettings(max_events_per_day=0)
    with pytest.raises(ValueError):
        RetentionSettings(max_total_disk_mb=0)


def test_min_event_speed_must_be_non_negative() -> None:
    with pytest.raises(ValueError):
        ServerSettings(min_event_speed_kph=-1.0)


def test_timezone_defaults_to_empty_meaning_utc() -> None:
    assert ServerSettings().timezone == ""
    assert ServerSettings(timezone="America/New_York").timezone == "America/New_York"


def test_field_labels_is_non_empty_dict() -> None:
    """FIELD_LABELS should be a non-empty dict with string keys and 2-tuple values."""
    assert isinstance(FIELD_LABELS, dict)
    assert len(FIELD_LABELS) > 0
    for key, value in FIELD_LABELS.items():
        assert isinstance(key, str)
        label, help_text = value
        assert isinstance(label, str)
        assert isinstance(help_text, str)


def test_alerts_defaults_are_off_and_safe() -> None:
    from curbcam.config.schema import AlertsSettings, Settings

    a = Settings().alerts
    assert a.enabled is False
    assert a.ntfy_enabled is False and a.webhook_enabled is False and a.mqtt_enabled is False
    assert a.ntfy_server == "https://ntfy.sh"
    assert a.mqtt_port == 1883
    assert a.mqtt_cooldown_s == 0  # 0 = no throttle, every qualifying event
    assert a.ntfy_cooldown_s == 60
    assert a.base_url == "http://curbcam.local:8080"
    # cooldown / threshold validation
    with pytest.raises(ValueError):
        AlertsSettings(min_speed_kph=-1.0)
    with pytest.raises(ValueError):
        AlertsSettings(ntfy_cooldown_s=-1)


def test_alerts_env_override_shadows_field(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from curbcam.config.schema import Settings

    monkeypatch.setenv("CURBCAM_ALERTS__WEBHOOK_URL", "https://example.test/hook")
    monkeypatch.setenv("CURBCAM_ALERTS__ENABLED", "true")
    s = Settings()
    assert s.alerts.webhook_url == "https://example.test/hook"
    assert s.alerts.enabled is True
