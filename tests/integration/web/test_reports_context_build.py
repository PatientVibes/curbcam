"""Direct coverage of reports.build_context (the view-model logic the plan left
exercised only indirectly). Uses the FileReplay-backed supervisor fixture so the
real EventRepo aggregations feed the context builder."""

from __future__ import annotations

import datetime as dt

from curbcam.web.reports import build_context


def _seed(supervisor) -> None:  # type: ignore[no-untyped-def]
    # Three events, same hour, speeds 20/30/40 kph, two L2R + one R2L.
    for speed, direction in [(20.0, "L2R"), (30.0, "R2L"), (40.0, "L2R")]:
        supervisor.events.save(
            ts_utc=dt.datetime(2026, 5, 28, 10, 0, 0),
            speed_kph=speed,
            direction=direction,
            frame_count=10,
            track_len_px=100,
            image_path="e.jpg",
            thumb_path="t.jpg",
            calibration_id=None,
        )


def test_build_context_aggregates_and_shapes_for_template(supervisor) -> None:  # type: ignore[no-untyped-def]
    _seed(supervisor)
    ctx = build_context(supervisor, "all")

    assert ctx["window"] == "all"
    assert ctx["units"] == "kph"  # fixture default; no conversion applied
    assert ctx["summary"]["count"] == 3
    assert ctx["summary"]["median"] == 30.0
    assert ctx["summary"]["max"] == 40.0
    # busiest hour derived from the by-hour aggregation
    assert ctx["busiest_hour"] == 10
    # per-direction split
    assert ctx["by_direction"]["L2R"]["count"] == 2
    assert ctx["by_direction"]["R2L"]["count"] == 1
    # histogram bars carry a percentage height in [0, 100] and never divide by zero
    assert ctx["histogram"]
    assert all(0 <= bar["pct"] <= 100 for bar in ctx["histogram"])
    # 24 hour slots, each a percentage
    assert len(ctx["hours"]) == 24


def test_build_context_empty_window_is_safe(supervisor) -> None:  # type: ignore[no-untyped-def]
    ctx = build_context(supervisor, "today")  # nothing seeded
    assert ctx["summary"]["count"] == 0
    assert ctx["summary"]["max"] == 0.0
    assert ctx["busiest_hour"] is None
    assert ctx["histogram"] == []


def test_build_context_unknown_window_defaults_to_7d(supervisor) -> None:  # type: ignore[no-untyped-def]
    ctx = build_context(supervisor, "nonsense")
    assert ctx["window"] == "7d"
