"""A field held read-only by an env var must say so, and say which var.

Previously such a field rendered with a bare "set via environment" badge. Anyone
who had set CURBCAM_CAMERA__SOURCE once in docker-compose and forgotten was left
with a permanently un-editable field and no stated cause -- a dead end in a UI
whose whole purpose is to avoid editing files.
"""

from __future__ import annotations

import pytest

from curbcam.web.settings_form import build_groups


def _find(groups: dict[str, list[dict[str, object]]], key: str) -> dict[str, object]:
    for fields in groups.values():
        for f in fields:
            if f["key"] == key:
                return f
    raise AssertionError(f"{key} not present in any settings group")


def test_field_is_not_marked_env_when_no_var_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CURBCAM_CAMERA__SOURCE", raising=False)
    field = _find(build_groups({}), "camera.source")
    assert field["env"] is False


def test_field_is_marked_env_and_names_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CURBCAM_CAMERA__SOURCE", "rtsp://cam.local/stream")
    field = _find(build_groups({}), "camera.source")
    assert field["env"] is True
    # The variable name is what makes the badge actionable -- without it the user
    # knows the field is locked but not what to unset.
    assert field["env_var"] == "CURBCAM_CAMERA__SOURCE"


def test_env_var_name_is_derived_for_every_field() -> None:
    """The name is computed, not hand-listed, so it cannot drift from the schema."""
    groups = build_groups({})
    for fields in groups.values():
        for f in fields:
            section, name = str(f["key"]).split(".", 1)
            assert f["env_var"] == f"CURBCAM_{section.upper()}__{name.upper()}"


def test_env_note_renders_with_the_variable_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end through Jinja: the rendered partial must contain both the
    variable name and a remedy, not just the badge."""
    monkeypatch.setenv("CURBCAM_SERVER__UNITS", "mph")
    from curbcam.web.templating import templates

    template = templates.env.get_template("partials/settings_form.html")
    html = template.render(groups=build_groups({}), saved=False)

    assert "CURBCAM_SERVER__UNITS" in html
    assert "read-only" in html
    # Tells the user how to regain control, not merely that they have lost it.
    assert "docker-compose" in html or ".env" in html
