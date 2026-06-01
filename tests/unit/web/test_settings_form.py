from curbcam.web.settings_form import build_groups


def test_alerts_group_present_with_bool_as_select() -> None:
    raw = {"alerts": {"enabled": True, "ntfy_enabled": False}}
    groups = build_groups(raw)
    assert "alerts" in groups
    by_key = {f["key"]: f for f in groups["alerts"]}
    enabled = by_key["alerts.enabled"]
    assert enabled["kind"] == "select"
    assert enabled["options"] == ["true", "false"]
    assert enabled["value"] == "true"  # normalized lowercase so the <option> matches
    assert by_key["alerts.ntfy_enabled"]["value"] == "false"
