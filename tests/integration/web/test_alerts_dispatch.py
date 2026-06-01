import datetime as dt

import pytest

from curbcam.config.schema import AlertsSettings


@pytest.mark.asyncio
async def test_dispatcher_fires_webhook_on_event_envelope(supervisor) -> None:  # type: ignore[no-untyped-def]
    # Configure alerts on, webhook enabled, in the supervisor's config store.
    raw = supervisor.config_store.load_raw()
    raw["alerts"] = AlertsSettings(
        enabled=True, webhook_enabled=True, webhook_url="https://hook.test/x", min_speed_kph=0.0
    ).model_dump(mode="json")
    supervisor.config_store.save_raw(raw)

    from curbcam.alerts.dispatcher import AlertDispatcher

    class _Resp:
        def raise_for_status(self) -> None:
            pass

    class _Client:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def post(self, url, **kwargs):  # type: ignore[no-untyped-def]
            self.calls.append(url)
            return _Resp()

        async def aclose(self) -> None:
            pass

    client = _Client()
    d = AlertDispatcher(
        supervisor.config_store, supervisor.bus, http_client=client, clock=lambda: 0.0
    )
    d.refresh()
    await d.handle(
        {"id": 1, "speed_kph": 80.0, "direction": "L2R", "ts_utc": dt.datetime.now().isoformat()}
    )
    assert client.calls == ["https://hook.test/x"]
