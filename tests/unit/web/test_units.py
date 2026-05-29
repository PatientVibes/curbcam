import pytest

from curbcam.web.units import distance_to_mm, format_speed, kph_to_display


def test_kph_passthrough() -> None:
    assert kph_to_display(50.0, "kph") == pytest.approx(50.0)


def test_kph_to_mph() -> None:
    assert kph_to_display(50.0, "mph") == pytest.approx(31.0686, rel=1e-4)


def test_format_speed_includes_units() -> None:
    assert format_speed(50.0, "kph") == "50.0 kph"
    assert format_speed(50.0, "mph") == "31.1 mph"


def test_distance_to_mm_all_units() -> None:
    assert distance_to_mm(1, "mm") == pytest.approx(1.0)
    assert distance_to_mm(1, "in") == pytest.approx(25.4)
    assert distance_to_mm(1, "ft") == pytest.approx(304.8)
    assert distance_to_mm(1, "m") == pytest.approx(1000.0)


def test_distance_to_mm_rejects_unknown_unit() -> None:
    with pytest.raises(KeyError):
        distance_to_mm(1, "league")
