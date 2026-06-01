import pytest

from curbcam.alerts.dispatcher import AlertDispatcher
from curbcam.config.schema import AlertsSettings, Settings


class _FakeStore:
    def __init__(self, alerts: AlertsSettings, units: str = "kph") -> None:
        self._s = Settings().model_copy(
            update={
                "alerts": alerts,
                "server": Settings().server.model_copy(update={"units": units}),
            }
        )

    def set(self, alerts: AlertsSettings) -> None:
        self._s = self._s.model_copy(update={"alerts": alerts})

    def load(self) -> Settings:
        return self._s


class _Resp:
    def raise_for_status(self) -> None:
        pass


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def post(self, url, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(url)
        return _Resp()

    async def aclose(self) -> None:
        pass


def _disp(store, client, clock):  # type: ignore[no-untyped-def]
    return AlertDispatcher(store, bus=None, http_client=client, clock=clock)


EVENT = {"id": 1, "speed_kph": 50.0, "direction": "L2R", "ts_utc": "2026-06-01T00:00:00"}


@pytest.mark.asyncio
async def test_no_fire_when_disabled() -> None:
    store = _FakeStore(AlertsSettings(enabled=False, ntfy_enabled=True, ntfy_topic="t"))
    c = _FakeClient()
    await _disp(store, c, lambda: 0.0).handle(EVENT)
    assert c.calls == []


@pytest.mark.asyncio
async def test_no_fire_below_threshold() -> None:
    store = _FakeStore(
        AlertsSettings(enabled=True, min_speed_kph=60.0, ntfy_enabled=True, ntfy_topic="t")
    )
    c = _FakeClient()
    await _disp(store, c, lambda: 0.0).handle(EVENT)
    assert c.calls == []


@pytest.mark.asyncio
async def test_fires_ntfy_when_qualifying() -> None:
    store = _FakeStore(
        AlertsSettings(enabled=True, ntfy_enabled=True, ntfy_topic="t", ntfy_server="https://n")
    )
    c = _FakeClient()
    await _disp(store, c, lambda: 0.0).handle(EVENT)
    assert c.calls == ["https://n/t"]


@pytest.mark.asyncio
async def test_cooldown_suppresses_then_allows() -> None:
    store = _FakeStore(
        AlertsSettings(enabled=True, ntfy_enabled=True, ntfy_topic="t", ntfy_cooldown_s=60)
    )
    c = _FakeClient()
    now = {"t": 0.0}
    d = _disp(store, c, lambda: now["t"])
    await d.handle(EVENT)  # fires
    now["t"] = 30.0
    await d.handle(EVENT)  # within cooldown -> suppressed
    now["t"] = 61.0
    await d.handle(EVENT)  # past cooldown -> fires
    assert len(c.calls) == 2


@pytest.mark.asyncio
async def test_cooldown_zero_fires_every_event() -> None:
    store = _FakeStore(
        AlertsSettings(
            enabled=True, webhook_enabled=True, webhook_url="https://h", webhook_cooldown_s=0
        )
    )
    c = _FakeClient()
    d = _disp(store, c, lambda: 0.0)
    await d.handle(EVENT)
    await d.handle(EVENT)
    assert c.calls == ["https://h", "https://h"]


@pytest.mark.asyncio
async def test_channel_failure_is_isolated() -> None:
    class _BoomClient(_FakeClient):
        async def post(self, url, **kwargs):  # type: ignore[no-untyped-def]
            if "boom" in url:
                raise RuntimeError("down")
            return await super().post(url, **kwargs)

    store = _FakeStore(
        AlertsSettings(
            enabled=True,
            ntfy_enabled=True,
            ntfy_topic="boom",
            ntfy_server="https://n",
            webhook_enabled=True,
            webhook_url="https://ok",
        )
    )
    c = _BoomClient()
    await _disp(store, c, lambda: 0.0).handle(EVENT)
    assert c.calls == ["https://ok"]  # webhook still fired despite ntfy failure


@pytest.mark.asyncio
async def test_refresh_reloads_cached_config() -> None:
    store = _FakeStore(AlertsSettings(enabled=False))
    c = _FakeClient()
    d = _disp(store, c, lambda: 0.0)
    await d.handle(EVENT)
    assert c.calls == []
    store.set(AlertsSettings(enabled=True, webhook_enabled=True, webhook_url="https://h"))
    d.refresh()
    await d.handle(EVENT)
    assert c.calls == ["https://h"]
