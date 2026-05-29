"""Composition root: build the FastAPI app from an injected Supervisor.

Pure function of the Supervisor so the whole app is testable with a
FileReplaySource-backed supervisor (no hardware). Startup binds the event
loop to the bus and starts the pipeline; shutdown stops it.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from curbcam.web.routes import debug
from curbcam.web.supervisor import Supervisor


def create_app(supervisor: Supervisor) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        supervisor.bus.bind_loop(asyncio.get_running_loop())
        supervisor.start()
        try:
            yield
        finally:
            supervisor.stop()

    app = FastAPI(title="curbcam", lifespan=lifespan)
    app.state.supervisor = supervisor
    app.include_router(debug.router)
    return app
