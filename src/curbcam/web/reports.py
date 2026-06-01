"""Report window parsing + view-model assembly for the reports dashboard."""

from __future__ import annotations

import datetime as dt
from typing import Any

from curbcam.web.supervisor import Supervisor
from curbcam.web.units import kph_to_display

WINDOWS = ("today", "7d", "30d", "all")
_BIN_KPH = 5.0


def window_start(window: str, now: dt.datetime) -> dt.datetime | None:
    if window == "today":
        return dt.datetime.combine(now.date(), dt.time.min)
    if window == "30d":
        return now - dt.timedelta(days=30)
    if window == "all":
        return None
    return now - dt.timedelta(days=7)  # 7d is the default for "7d" and anything unknown


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def build_context(sup: Supervisor, window: str) -> dict[str, Any]:
    if window not in WINDOWS:
        window = "7d"
    units = sup.config_store.load().server.units
    start = window_start(window, _now_utc())
    repo = sup.events

    summary = repo.summary(start)
    bins = repo.speed_histogram(start, _BIN_KPH)
    by_hour = repo.by_hour(start)
    daily = repo.daily_counts(start)
    by_dir = repo.by_direction(start)

    def disp(kph: float) -> float:
        return round(kph_to_display(kph, units), 1)

    # Histogram bars (display-unit bucket labels, % heights for inline SVG).
    hist_max = max(bins.values(), default=0)
    histogram = [
        {
            "label": f"{disp(lo):.0f}",
            "count": bins[lo],
            "pct": (bins[lo] / hist_max * 100) if hist_max else 0,
        }
        for lo in sorted(bins)
    ]

    hour_max = max(by_hour, default=0)
    hours = [
        {"hour": h, "count": c, "pct": (c / hour_max * 100) if hour_max else 0}
        for h, c in enumerate(by_hour)
    ]
    busiest_hour = max(range(24), key=lambda h: by_hour[h]) if summary.count else None

    # Daily trend polyline points over a 100x100 viewBox.
    day_max = max((n for _, n in daily), default=0)
    n = len(daily)
    trend_points = " ".join(
        f"{(i / (n - 1) * 100) if n > 1 else 0:.1f},{100 - (cnt / day_max * 100 if day_max else 0):.1f}"
        for i, (_, cnt) in enumerate(daily)
    )

    return {
        "window": window,
        "windows": WINDOWS,
        "units": units,
        "summary": {
            "count": summary.count,
            "median": disp(summary.median_kph),
            "p85": disp(summary.p85_kph),
            "max": disp(summary.max_kph),
        },
        "histogram": histogram,
        "hours": hours,
        "busiest_hour": busiest_hour,
        "daily": [{"date": d, "count": c} for d, c in daily],
        "trend_points": trend_points,
        "by_direction": {
            "L2R": {"count": by_dir["L2R"][0], "median": disp(by_dir["L2R"][1])},
            "R2L": {"count": by_dir["R2L"][0], "median": disp(by_dir["R2L"][1])},
        },
    }
