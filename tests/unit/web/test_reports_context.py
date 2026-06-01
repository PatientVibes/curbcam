import datetime as dt

from curbcam.web.reports import window_start


def test_window_start_mappings() -> None:
    now = dt.datetime(2026, 6, 1, 15, 30, 0)
    assert window_start("today", now) == dt.datetime(2026, 6, 1, 0, 0, 0)
    assert window_start("7d", now) == now - dt.timedelta(days=7)
    assert window_start("30d", now) == now - dt.timedelta(days=30)
    assert window_start("all", now) is None
    assert window_start("garbage", now) == now - dt.timedelta(days=7)  # default 7d
