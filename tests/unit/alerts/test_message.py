from curbcam.alerts.message import build_payload, build_text
from curbcam.config.schema import AlertsSettings

EVENT = {"id": 7, "speed_kph": 61.2, "direction": "L2R", "ts_utc": "2026-06-01T19:14:02"}


def test_build_payload_converts_to_display_units_and_links() -> None:
    s = AlertsSettings(base_url="http://cam.local:8080")
    p = build_payload(s, EVENT, "mph")
    assert p["event_id"] == 7
    assert p["speed_kph"] == 61.2
    assert p["speed_display"] == 38.0  # 61.2 / 1.609344 -> 38.0
    assert p["units"] == "mph"
    assert p["direction"] == "L2R"
    assert p["url"] == "http://cam.local:8080/events"


def test_build_payload_blank_base_url_omits_link() -> None:
    p = build_payload(AlertsSettings(base_url=""), EVENT, "kph")
    assert p["url"] == ""


def test_build_text_is_speed_units_direction() -> None:
    s = AlertsSettings(base_url="")
    assert build_text(build_payload(s, EVENT, "mph")) == "38 mph L2R"
