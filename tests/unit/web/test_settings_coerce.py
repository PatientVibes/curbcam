from curbcam.web.routes.settings import _coerce


def test_coerce_boolean_keys_to_real_bool() -> None:
    assert _coerce("alerts.enabled", "true") is True
    assert _coerce("alerts.enabled", "false") is False
    assert _coerce("alerts.mqtt_enabled", "false") is False


def test_coerce_passes_non_bool_through() -> None:
    assert _coerce("alerts.ntfy_topic", "street") == "street"
    assert _coerce("camera.resolution", "1280x720") == [1280, 720]
