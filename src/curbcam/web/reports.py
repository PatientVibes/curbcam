"""Report window parsing + view-model assembly for the reports dashboard."""

from __future__ import annotations

import datetime as dt
from typing import Any

from curbcam.localtime import to_local, zone
from curbcam.web.supervisor import Supervisor
from curbcam.web.units import kph_to_display

WINDOWS = ("today", "7d", "30d", "all")
_BIN_DISPLAY = 5  # histogram bucket width, in the user's display units (5 mph / 5 kph)


def window_start(window: str, now_utc: dt.datetime, tz: dt.tzinfo) -> dt.datetime | None:
    if window == "today":
        # Local midnight today, expressed back in naive UTC for DB filtering.
        local_midnight = to_local(now_utc, tz).replace(hour=0, minute=0, second=0, microsecond=0)
        return local_midnight.astimezone(dt.UTC).replace(tzinfo=None)
    if window == "30d":
        return now_utc - dt.timedelta(days=30)
    if window == "all":
        return None
    return now_utc - dt.timedelta(days=7)  # default for "7d" and anything unknown


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def _fill_daily(
    present: list[tuple[str, int]], start: dt.datetime | None, today: dt.date
) -> list[tuple[str, int]]:
    """Expand per-day counts to one entry per calendar day across the window.

    ``daily_counts`` only returns days that HAVE events, so plotting them
    directly spaces sparse days evenly and visually hides multi-day gaps. Filling
    the zero-event days makes the trend's x-axis reflect real elapsed time.
    """
    counts = {d: n for d, n in present}
    if start is not None:
        span_start = start.date()
    elif present:
        span_start = dt.date.fromisoformat(present[0][0])
    else:
        return []
    out: list[tuple[str, int]] = []
    day = span_start
    while day <= today:
        key = day.isoformat()
        out.append((key, counts.get(key, 0)))
        day += dt.timedelta(days=1)
    return out


def build_context(sup: Supervisor, window: str) -> dict[str, Any]:
    if window not in WINDOWS:
        window = "7d"
    server = sup.config_store.load().server
    units = server.units
    tz = zone(server.timezone)
    now_utc = _now_utc()
    start = window_start(window, now_utc, tz)
    repo = sup.events

    summary = repo.summary(start)
    by_hour = repo.by_hour(start, tz)
    daily = _fill_daily(repo.daily_counts(start, tz), start, to_local(now_utc, tz).date())
    by_dir = repo.by_direction(start)

    def disp(kph: float) -> float:
        return round(kph_to_display(kph, units), 1)

    # Histogram: bucket in the user's DISPLAY units so mph users get round 5-mph
    # bins, not 5-kph bins relabeled into uneven mph (spec §5.3).
    bins: dict[int, int] = {}
    for kph in repo.speeds_since(start):
        lo = int(kph_to_display(kph, units) // _BIN_DISPLAY) * _BIN_DISPLAY
        bins[lo] = bins.get(lo, 0) + 1
    hist_max = max(bins.values(), default=0)
    histogram = [
        {
            "label": str(lo),
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
