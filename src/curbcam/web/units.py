"""Display-unit conversion + real-world distance conversion.

Speeds are always stored in kph (the pipeline's native unit). The display
unit (kph | mph) is a server.units setting applied at render/export time.
Calibration distances are entered in m/ft/in/mm and converted to mm.
"""

from __future__ import annotations

_KPH_PER_MPH = 1.609344
_TO_MM = {"mm": 1.0, "in": 25.4, "ft": 304.8, "m": 1000.0}


def kph_to_display(kph: float, units: str) -> float:
    return kph if units == "kph" else kph / _KPH_PER_MPH


def format_speed(kph: float, units: str) -> str:
    return f"{kph_to_display(kph, units):.1f} {units}"


def display_to_kph(value: float, units: str) -> float:
    return value if units == "kph" else value * _KPH_PER_MPH


def distance_to_mm(value: float, unit: str) -> float:
    return value * _TO_MM[unit]
