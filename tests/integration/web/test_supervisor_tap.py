def test_viewer_and_stats_delegate(supervisor) -> None:  # type: ignore[no-untyped-def]
    supervisor.start()
    try:
        supervisor.add_viewer()
        st = supervisor.stats()
        assert st["running"] is True
        assert st["viewers"] >= 1
        assert "fps" in st and "tracking" in st
    finally:
        supervisor.remove_viewer()
        supervisor.stop()


def test_capture_still_returns_none_when_stopped(supervisor) -> None:  # type: ignore[no-untyped-def]
    assert supervisor.capture_still() is None
