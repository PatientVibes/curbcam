"""Every settings field must be reachable from the UI.

curbcam is meant to be configurable without editing YAML or code, which means a
new field in ``schema.py`` has to be wired up in two more places before it is
actually usable:

    schema.py         the field itself
    defaults.py       FIELD_LABELS -- label + help text
    settings_form.py  PRIMARY / ADVANCED / ALERTS -- group + input kind

Miss the second and the settings page renders the raw dotted key as the label.
Miss the third and the field silently does not appear at all -- the only way to
change it becomes hand-editing curbcam.yaml, which is exactly what the UI exists
to avoid.

These tests make that a CI failure instead of a silent regression. The docstring
in defaults.py has promised this check since MVP-2.
"""

from __future__ import annotations

from curbcam.config.defaults import FIELD_LABELS
from curbcam.config.schema import Settings
from curbcam.web.settings_form import ADVANCED, ALERTS, PRIMARY

# detector.crop is set by the alignment wizard (drag a rectangle over the live
# frame), not by a form input -- a raw pixel rect is not something anyone should
# type. It is deliberately absent from the form groups.
WIZARD_MANAGED: frozenset[str] = frozenset({"detector.crop"})


def _schema_keys() -> set[str]:
    """Dotted keys of every leaf field on Settings, e.g. "camera.source"."""
    keys: set[str] = set()
    for section, field in Settings.model_fields.items():
        sub_fields = getattr(field.annotation, "model_fields", None)
        if sub_fields:
            keys.update(f"{section}.{name}" for name in sub_fields)
    return keys


def _form_keys() -> set[str]:
    return {key for key, _kind in (*PRIMARY, *ADVANCED, *ALERTS)}


def test_every_schema_field_has_a_label() -> None:
    missing = sorted(_schema_keys() - set(FIELD_LABELS))
    assert not missing, (
        f"Settings fields with no entry in FIELD_LABELS: {missing}. "
        "Add a (label, help) row to curbcam/config/defaults.py -- without one the "
        "settings page shows the raw dotted key as the field label."
    )


def test_every_schema_field_appears_in_a_form_group() -> None:
    missing = sorted(_schema_keys() - _form_keys() - WIZARD_MANAGED)
    assert not missing, (
        f"Settings fields not in any settings_form group: {missing}. "
        "Add each to PRIMARY, ADVANCED or ALERTS in curbcam/web/settings_form.py -- "
        "a field that is in no group cannot be changed from the UI at all, only by "
        "hand-editing curbcam.yaml."
    )


def test_no_labels_for_fields_that_no_longer_exist() -> None:
    """Catches the reverse drift: a field renamed or removed from the schema
    while its label lingers, which quietly becomes dead documentation."""
    orphans = sorted(set(FIELD_LABELS) - _schema_keys())
    assert not orphans, (
        f"FIELD_LABELS entries with no matching Settings field: {orphans}. "
        "Remove them, or fix the key if the field was renamed."
    )


def test_no_form_entries_for_fields_that_no_longer_exist() -> None:
    orphans = sorted(_form_keys() - _schema_keys())
    assert not orphans, (
        f"settings_form group entries with no matching Settings field: {orphans}. "
        "A form field with no schema backing renders but silently fails to save."
    )


def test_every_field_has_nonempty_label_and_help() -> None:
    """A blank label or help string passes the coverage checks above while still
    leaving the user with nothing to go on."""
    blank = sorted(
        key
        for key, (label, help_text) in FIELD_LABELS.items()
        if not label.strip() or not help_text.strip()
    )
    assert not blank, f"FIELD_LABELS entries with an empty label or help text: {blank}"


def test_wizard_managed_fields_really_are_in_the_schema() -> None:
    """Guards the exemption list itself -- if detector.crop were renamed, the
    exemption would silently start excusing nothing."""
    stale = sorted(WIZARD_MANAGED - _schema_keys())
    assert not stale, (
        f"WIZARD_MANAGED lists fields that are not in Settings: {stale}. "
        "Update the exemption list in this test."
    )
