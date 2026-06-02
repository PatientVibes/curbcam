import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from curbcam.web.reports import percentile, window_start


def test_percentile_linear_interpolation() -> None:
    vals = [20.0, 25.0, 30.0, 35.0, 40.0, 45.0]
    assert percentile(vals, 50) == pytest.approx(32.5)  # between 30 and 35
    assert percentile(vals, 85) == pytest.approx(41.25)  # between 40 and 45
    assert percentile(vals, 100) == 45.0
    assert percentile([], 50) == 0.0


def test_window_start_mappings_utc() -> None:
    now = dt.datetime(2026, 6, 1, 15, 30, 0)
    assert window_start("today", now, dt.UTC) == dt.datetime(2026, 6, 1, 0, 0, 0)
    assert window_start("7d", now, dt.UTC) == now - dt.timedelta(days=7)
    assert window_start("30d", now, dt.UTC) == now - dt.timedelta(days=30)
    assert window_start("all", now, dt.UTC) is None
    assert window_start("garbage", now, dt.UTC) == now - dt.timedelta(days=7)  # default 7d


def test_today_window_uses_local_midnight() -> None:
    # 06:30 UTC on 2026-06-01 is 23:30 on 2026-05-31 in Los Angeles (UTC-7 in
    # summer). "Today" must start at LOCAL midnight (2026-06-01 00:00 -07:00 =
    # 2026-06-01 07:00 UTC), not UTC midnight.
    now_utc = dt.datetime(2026, 6, 1, 6, 30, 0)
    la = ZoneInfo("America/Los_Angeles")
    # local time is still 2026-05-31, so local midnight is 2026-05-31 00:00 -07:00
    assert window_start("today", now_utc, la) == dt.datetime(2026, 5, 31, 7, 0, 0)
