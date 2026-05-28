"""The single orchestrator: camera → detector → storage.

Two flavours of operation:
- ``run_until_camera_exhausted()`` — synchronous, used by the CLI's
  ``curbcam detect`` command and by tests with a FileReplaySource.
- ``run_in_background_thread()`` — used by the MVP-2 web server. Returns
  a started thread; .stop() to ask it to wind down.

Per design spec §4.3: this is the ONLY module that wires the three
collaborators. The detector knows nothing about storage; storage knows
nothing about cameras.
"""

import datetime as dt
import logging
import threading
import time

import cv2

from curbcam.camera.base import Camera
from curbcam.config.schema import Settings
from curbcam.detector.calibration import Calibration as CalDC
from curbcam.detector.calibration import speed_from_track
from curbcam.detector.motion import find_motion
from curbcam.detector.tracker import Tracker
from curbcam.pipeline.events import EventBus, EventEnvelope
from curbcam.storage.db import Database
from curbcam.storage.media import MediaWriter
from curbcam.storage.models import Event
from curbcam.storage.repositories import CalibrationRepo

log = logging.getLogger(__name__)


class PipelineRunner:
    def __init__(
        self,
        *,
        camera: Camera,
        db: Database,
        calibration_repo: CalibrationRepo,
        media: MediaWriter,
        bus: EventBus,
        settings: Settings,
    ) -> None:
        self._camera = camera
        self._db = db
        self._calibrations = calibration_repo
        self._media = media
        self._bus = bus
        self._settings = settings
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        self._tracker = Tracker(
            max_dist_px=settings.detector.max_dist_px,
            min_track_frames=settings.detector.min_track_frames,
        )

    def run_until_camera_exhausted(self) -> None:
        self._camera.open()
        try:
            prev_gray = None
            last_full_frame = None
            while not self._stop.is_set():
                got = self._camera.read()
                if got is None:
                    break
                frame_bgr, ts = got
                last_full_frame = frame_bgr
                curr_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
                if prev_gray is not None:
                    self._process_frame(prev_gray, curr_gray, frame_bgr, frame_ts=ts)
                prev_gray = curr_gray
            # Source exhausted — flush any in-flight track.
            if last_full_frame is not None:
                for track in self._tracker.flush():
                    self._persist_track(track, last_full_frame)
        finally:
            self._camera.close()

    def run_in_background_thread(self) -> threading.Thread:
        if self._thread is not None and self._thread.is_alive():
            return self._thread
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop_with_reconnect, name="curbcam-runner", daemon=True
        )
        self._thread.start()
        return self._thread

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _loop_with_reconnect(self) -> None:
        """Reconnect loop for persistent sources; one-shot for finite sources.

        A live camera (USB, RTSP, picamera2, looping replay) has
        ``is_persistent = True``: when read() returns None we treat it
        as a transient failure, sleep briefly, and reopen. A finite
        source (non-looping FileReplaySource) has
        ``is_persistent = False``: when run_until_camera_exhausted
        returns normally, we exit the loop. Either way, exceptions are
        logged and retried for persistent sources only.
        """
        while not self._stop.is_set():
            try:
                self.run_until_camera_exhausted()
            except Exception:
                log.exception("Pipeline crashed")
                # Drop any in-flight tracks from the crashed run — their
                # frame_ts values are stale, and matching new detections
                # against them would produce garbage speed readings on the
                # very first frame after reconnect.
                self._tracker = Tracker(
                    max_dist_px=self._settings.detector.max_dist_px,
                    min_track_frames=self._settings.detector.min_track_frames,
                )
                if not self._camera.is_persistent:
                    return
                time.sleep(2.0)
                continue
            if not self._camera.is_persistent:
                return
            time.sleep(0.5)

    # -- internals --

    def _process_frame(self, prev_gray, curr_gray, frame_bgr, *, frame_ts: float) -> None:  # type: ignore[no-untyped-def]
        detections = find_motion(
            prev_gray,
            curr_gray,
            min_area_px=self._settings.detector.min_area_px,
            crop=self._settings.detector.crop,
            frame_ts=frame_ts,
        )
        finalised = self._tracker.update(detections)
        for track in finalised:
            self._persist_track(track, frame_bgr)

    def _persist_track(self, track, last_frame_bgr) -> None:  # type: ignore[no-untyped-def]
        cal = self._calibrations.get_active()
        if cal is None:
            log.info("Track finalised but no active calibration; skipping")
            return
        cal_dc = CalDC(
            mm_per_px_l2r=float(cal.mm_per_px_l2r), mm_per_px_r2l=float(cal.mm_per_px_r2l)
        )
        speed = speed_from_track(track, cal_dc)
        if speed is None:
            return
        if speed < self._settings.server.min_event_speed_kph:
            log.info("Track below min_event_speed_kph (%.1f); skipping", speed)
            return

        ts_utc = dt.datetime.now(dt.UTC).replace(tzinfo=None)
        with self._db.session() as s:
            ev = Event(
                ts_utc=ts_utc,
                speed_kph=float(speed),
                # Tracker._finalise always sets direction; `or` is purely defensive
                # against an unexpected None from a future refactor.
                direction=track.direction or "L2R",
                frame_count=len(track.detections),
                track_len_px=int(
                    abs(track.detections[-1].centroid[0] - track.detections[0].centroid[0])
                ),
                image_path="",
                thumb_path="",
                calibration_id=cal.id,
            )
            s.add(ev)
            s.flush()
            rel_full, rel_thumb = self._media.save_event_image(
                frame=last_frame_bgr,
                event_id=ev.id,
                ts_utc=ts_utc,
                speed_kph=float(speed),
                direction=ev.direction,
            )
            ev.image_path = rel_full
            ev.thumb_path = rel_thumb
            s.commit()
            event_id = ev.id

        self._bus.publish_threadsafe(
            EventEnvelope(
                kind="event",
                payload={
                    "id": event_id,
                    "speed_kph": float(speed),
                    "direction": track.direction,
                    "image_path": rel_full,
                    "thumb_path": rel_thumb,
                    "ts_utc": ts_utc.isoformat(),
                },
            )
        )
        log.info("Event %d persisted: %.1f kph %s", event_id, speed, track.direction)
