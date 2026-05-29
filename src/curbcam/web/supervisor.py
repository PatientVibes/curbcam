"""Owns all long-lived web-process state and the pipeline lifecycle.

A single Supervisor instance is held on app.state. Routes depend only on
it (never on globals). start/stop/restart are serialized by a lock so two
near-simultaneous settings saves cannot race to replace the runner thread
(spec §4 concurrency invariant). The live-frame tap (latest_frame /
capture_still / viewers / overlay / stats) is wired in Slice C once the
PipelineRunner exposes it; until then those return safe defaults.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from curbcam.camera.factory import camera_from_source
from curbcam.config.store import ConfigStore
from curbcam.pipeline.events import EventBus, EventEnvelope
from curbcam.pipeline.runner import PipelineRunner
from curbcam.storage.db import Database
from curbcam.storage.media import MediaWriter
from curbcam.storage.repositories import CalibrationRepo, EventRepo


class Supervisor:
    def __init__(
        self,
        *,
        config_store: ConfigStore,
        db: Database,
        bus: EventBus,
        media_root: Path,
    ) -> None:
        self._config_store = config_store
        self._db = db
        self._bus = bus
        self._media_root = media_root
        self._media = MediaWriter(media_root)
        self.calibrations = CalibrationRepo(db)
        self.events = EventRepo(db)
        self._runner: PipelineRunner | None = None
        self._lock = threading.Lock()
        self._started_at: float | None = None

    # -- exposed collaborators (read-only access for routes) --
    @property
    def bus(self) -> EventBus:
        return self._bus

    @property
    def db(self) -> Database:
        return self._db

    @property
    def config_store(self) -> ConfigStore:
        return self._config_store

    @property
    def media_root(self) -> Path:
        return self._media_root

    # -- lifecycle --
    def _build_runner(self, settings) -> PipelineRunner:  # type: ignore[no-untyped-def]
        cam = camera_from_source(
            settings.camera.source,
            resolution=settings.camera.resolution,
            fps_target=settings.camera.fps_target,
            loop=True,
        )
        return PipelineRunner(
            camera=cam,
            db=self._db,
            calibration_repo=self.calibrations,
            media=self._media,
            bus=self._bus,
            settings=settings,
        )

    def start(self) -> None:
        with self._lock:
            if self._runner is not None:
                return
            settings = self._config_store.load()
            self._runner = self._build_runner(settings)
            self._runner.run_in_background_thread()
            self._started_at = time.monotonic()

    def stop(self) -> None:
        with self._lock:
            if self._runner is not None:
                self._runner.stop()
                self._runner = None

    def restart(self) -> None:
        with self._lock:
            if self._runner is not None:
                self._runner.stop()
            settings = self._config_store.load()
            self._runner = self._build_runner(settings)
            self._runner.run_in_background_thread()
            self._started_at = time.monotonic()
        # Notify connected UIs after releasing the lock.
        self._bus.publish_threadsafe(EventEnvelope(kind="settings_changed", payload={}))

    def stats(self) -> dict[str, object]:
        uptime = 0.0 if self._started_at is None else time.monotonic() - self._started_at
        return {"uptime_s": round(uptime, 1), "running": self._runner is not None}
