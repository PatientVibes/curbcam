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


def test_histogram_buckets_in_display_units_not_kph(supervisor) -> None:  # type: ignore[no-untyped-def]
    # Switch the device to mph, then seed speeds whose mph values land in
    # distinct 5-mph buckets. Bucketing in kph (the old bug) would relabel
    # 5-kph buckets into uneven non-round mph ticks.
    raw = supervisor.config_store.load_raw()
    raw.setdefault("server", {})["units"] = "mph"
    supervisor.config_store.save_raw(raw)
    for kph in (16.1, 17.7, 32.2):  # ~10.0, ~11.0, ~20.0 mph
        supervisor.events.save(
            ts_utc=dt.datetime(2026, 5, 28, 10, 0, 0),
            speed_kph=kph,
            direction="L2R",
            frame_count=10,
            track_len_px=100,
            image_path="e.jpg",
            thumb_path="t.jpg",
            calibration_id=None,
        )
    ctx = build_context(supervisor, "all")
    assert ctx["units"] == "mph"
    labels = [bar["label"] for bar in ctx["histogram"]]
    # 10 & 11 mph -> the "10" bucket (2 events); 20 mph -> the "20" bucket.
    assert labels == ["10", "20"]
    counts = {bar["label"]: bar["count"] for bar in ctx["histogram"]}
    assert counts == {"10": 2, "20": 1}
    # every label is a clean multiple of the 5-unit bin width
    assert all(int(lbl) % 5 == 0 for lbl in labels)


def test_daily_trend_fills_zero_event_days(supervisor) -> None:  # type: ignore[no-untyped-def]
    import curbcam.web.reports as reports_mod

    now = reports_mod._now_utc()
    # Events on two non-adjacent days inside a 7-day window.
    for delta in (1, 4):
        supervisor.events.save(
            ts_utc=now - dt.timedelta(days=delta),
            speed_kph=30.0,
            direction="L2R",
            frame_count=10,
            track_len_px=100,
            image_path="e.jpg",
            thumb_path="t.jpg",
            calibration_id=None,
        )
    ctx = build_context(supervisor, "7d")
    counts = {d["date"]: d["count"] for d in ctx["daily"]}
    # The gap day between the two active days is present and zero (not skipped).
    gap_day = (now - dt.timedelta(days=2)).date().isoformat()
    assert gap_day in counts
    assert counts[gap_day] == 0
    # Contiguous calendar coverage across the ~7-day window.
    assert len(ctx["daily"]) >= 7
