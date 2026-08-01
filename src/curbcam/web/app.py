"""Composition root: build the FastAPI app from an injected Supervisor.

Pure function of the Supervisor so the whole app is testable with a
FileReplaySource-backed supervisor (no hardware). Startup binds the event
loop to the bus and starts the pipeline; shutdown stops it.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from curbcam.web.routes import (
    alerts,
    auth,
    backup,
    calibration,
    crop,
    debug,
    events,
    health,
    pages,
    reports,
    settings,
    setup,
    stream,
)
from curbcam.web.supervisor import Supervisor


async def _stats_loop(supervisor: Supervisor) -> None:
    while True:
        await asyncio.sleep(1.0)
        supervisor.publish_stats()


def create_app(supervisor: Supervisor) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        from curbcam.alerts.dispatcher import AlertDispatcher

        supervisor.bus.bind_loop(asyncio.get_running_loop())
        supervisor.start()
        stats_task = asyncio.create_task(_stats_loop(supervisor))
        dispatcher = AlertDispatcher(supervisor.config_store, supervisor.bus)
        # Published on app.state so the test-alert route can reuse this exact
        # dispatcher -- same httpx client, same MQTT connection, same sender code
        # path. A test send that built its own dispatcher could pass while real
        # alerts fail, which would make the button actively misleading.
        app.state.alert_dispatcher = dispatcher
        alerts_task = asyncio.create_task(dispatcher.run())
        try:
            yield
        finally:
            app.state.alert_dispatcher = None
            stats_task.cancel()
            alerts_task.cancel()
            # Await the cancelled tasks before tearing down resources: aclose()
            # closes the httpx client the dispatcher may still be mid-send on,
            # and awaiting also retrieves the CancelledError so asyncio doesn't
            # log "Task exception was never retrieved".
            await asyncio.gather(stats_task, alerts_task, return_exceptions=True)
            await dispatcher.aclose()
            supervisor.stop()

    app = FastAPI(title="curbcam", lifespan=lifespan)
    app.state.supervisor = supervisor

    from curbcam.web.middleware import first_run_gate

    app.middleware("http")(first_run_gate)

    app.include_router(auth.router)
    app.include_router(debug.router)
    app.include_router(health.router)
    app.include_router(stream.router)
    app.include_router(events.router)
    app.include_router(reports.router)
    app.include_router(settings.router)
    app.include_router(alerts.router)
    app.include_router(backup.router)
    app.include_router(calibration.router)
    app.include_router(crop.router)
    app.include_router(setup.router)

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    # NB: media is NOT a StaticFiles mount — event images are private and are
    # served by an auth-protected /media route in pages.py (web spec §6). We still
    # ensure the directory exists so FileResponse has a root to resolve against.
    supervisor.media_root.mkdir(parents=True, exist_ok=True)
    app.include_router(pages.router)
    return app
