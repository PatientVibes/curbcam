"""The alert channel registry.

Adding a channel used to mean editing five files, and the easy one to forget was
a hard-coded list inside the dispatcher -- a channel could be fully configurable
in the UI and simply never fire, with nothing to say why.

These tests hold the registry to the contract the dispatcher, the settings form
and the test-alert endpoint all now depend on.
"""

from __future__ import annotations

from curbcam.alerts.registry import CHANNELS, CHANNELS_BY_NAME
from curbcam.config.defaults import FIELD_LABELS
from curbcam.config.schema import AlertsSettings
from curbcam.web.settings_form import ALERTS


def test_names_are_unique() -> None:
    names = [c.name for c in CHANNELS]
    assert len(names) == len(set(names))
    assert set(CHANNELS_BY_NAME) == set(names)


def test_accessors_work_against_a_default_settings_object() -> None:
    """Each spec reads its own fields off AlertsSettings, so a renamed field
    shows up here rather than as a channel that silently stops firing."""
    s = AlertsSettings()
    for spec in CHANNELS:
        assert isinstance(spec.enabled(s), bool)
        assert isinstance(spec.target(s), str)
        assert isinstance(spec.cooldown_s(s), int)


def test_all_channels_are_off_by_default() -> None:
    """A speed camera must not start notifying anyone until asked to."""
    s = AlertsSettings()
    assert not any(spec.enabled(s) for spec in CHANNELS)


def test_is_configured_requires_a_non_blank_target() -> None:
    s = AlertsSettings()
    for spec in CHANNELS:
        assert not spec.is_configured(s), f"{spec.name} claims to be configured by default"

    # Whitespace is not configuration -- a topic of " " would otherwise pass the
    # check and then fail at send time with a confusing transport error.
    assert not AlertsSettings(ntfy_topic="   ").ntfy_topic.strip()
    assert not CHANNELS_BY_NAME["ntfy"].is_configured(AlertsSettings(ntfy_topic="   "))
    assert CHANNELS_BY_NAME["ntfy"].is_configured(AlertsSettings(ntfy_topic="curbcam-abc"))


def test_every_channel_has_settings_fields_wired_to_the_ui() -> None:
    """A channel in the registry with no UI fields could never be configured."""
    form_keys = {key for key, _kind in ALERTS}
    for spec in CHANNELS:
        prefix = f"alerts.{spec.name}_"
        assert any(k.startswith(prefix) for k in form_keys), (
            f"channel {spec.name!r} has no alerts.{spec.name}_* fields in the settings form"
        )
        assert any(k.startswith(prefix) for k in FIELD_LABELS), (
            f"channel {spec.name!r} has no alerts.{spec.name}_* entries in FIELD_LABELS"
        )


def test_target_label_reads_naturally_in_an_error_message() -> None:
    """target_label is interpolated into 'No {label} set for {channel}. Save one
    first.', so it must be a human noun phrase rather than a field name.

    Acronyms are fine and preferable -- "No URL set for Webhook" reads better
    than "No url set". What must not appear is snake_case leaking from the
    schema, which would tell the user to go looking for a YAML key.
    """
    for spec in CHANNELS:
        assert spec.target_label, f"{spec.name} has no target_label"
        assert "_" not in spec.target_label, (
            f"{spec.name}: target_label {spec.target_label!r} looks like a field name"
        )
        # Sentence-cased or lowercase, never SHOUTING beyond a short acronym.
        assert not (spec.target_label.isupper() and len(spec.target_label) > 5)
