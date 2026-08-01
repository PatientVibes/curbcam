"""Report window parsing + view-model assembly for the reports dashboard."""

from __future__ import annotations

import datetime as dt
import math
from typing import Any

from curbcam.localtime import now_utc, to_local, zone
from curbcam.web.supervisor import Supervisor
from curbcam.web.units import display_speed

WINDOWS = ("today", "7d", "30d", "all")
_BIN_DISPLAY = 5  # histogram bucket width, in the user's display units (5 mph / 5 kph)


def percentile(sorted_vals: list[float], pct: float) -> float:
    """Linear-interpolated percentile (numpy 'linear' method)."""
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return sorted_vals[int(k)]
    return sorted_vals[lo] * (hi - k) + sorted_vals[hi] * (k - lo)


def _pct(value: float, peak: float) -> float:
    """Normalize a count to a 0-100 percentage of the series peak (chart bar
    height), guarding the empty/zero-peak case once."""
    return (value / peak * 100) if peak else 0


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
    now = now_utc()
    start = window_start(window, now, tz)
    repo = sup.events

    # One scan of (speed, direction); summary, histogram, and the per-direction
    # breakdown are all derived from it in Python.
    pairs = repo.speed_dirs_since(start)
    speeds = sorted(sp for sp, _ in pairs)
    count = len(speeds)

    by_hour = repo.by_hour(start, tz)
    daily = _fill_daily(repo.daily_counts(start, tz), start, to_local(now, tz).date())

    # Histogram: bucket in the user's DISPLAY units so mph users get round 5-mph
    # bins, not 5-kph bins relabeled into uneven mph (web spec §5.3).
    bins: dict[int, int] = {}
    for kph in speeds:
        lo = int(display_speed(kph, units) // _BIN_DISPLAY) * _BIN_DISPLAY
        bins[lo] = bins.get(lo, 0) + 1
    hist_max = max(bins.values(), default=0)
    histogram = [
        {"label": str(lo), "count": bins[lo], "pct": _pct(bins[lo], hist_max)}
        for lo in sorted(bins)
    ]

    hour_max = max(by_hour, default=0)
    hours = [{"hour": h, "count": c, "pct": _pct(c, hour_max)} for h, c in enumerate(by_hour)]
    busiest_hour = max(range(24), key=lambda h: by_hour[h]) if count else None

    # Daily trend polyline points over a 100x100 viewBox.
    day_max = max((c for _, c in daily), default=0)
    n = len(daily)
    trend_points = " ".join(
        f"{(i / (n - 1) * 100) if n > 1 else 0:.1f},{100 - _pct(c, day_max):.1f}"
        for i, (_, c) in enumerate(daily)
    )

    def dir_stats(direction: str) -> dict[str, float | int]:
        vals = sorted(sp for sp, d in pairs if d == direction)
        return {"count": len(vals), "median": display_speed(percentile(vals, 50), units)}

    return {
        "window": window,
        "windows": WINDOWS,
        "units": units,
        "summary": {
            "count": count,
            "median": display_speed(percentile(speeds, 50), units),
            "p85": display_speed(percentile(speeds, 85), units),
            "max": display_speed(speeds[-1], units) if count else 0.0,
        },
        "histogram": histogram,
        "hours": hours,
        "busiest_hour": busiest_hour,
        "daily": [{"date": d, "count": c} for d, c in daily],
        "trend_points": trend_points,
        "by_direction": {"L2R": dir_stats("L2R"), "R2L": dir_stats("R2L")},
    }
