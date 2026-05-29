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
import numpy as np

from curbcam.camera.base import Camera
from curbcam.config.schema import Settings
from curbcam.detector.calibration import Calibration as CalDC
from curbcam.detector.calibration import speed_from_track
from curbcam.detector.motion import find_motion
from curbcam.detector.tracker import Tracker
from curbcam.detector.types import Detection
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

        # -- live preview / stats tap (MVP-2) --
        self._frame_lock = threading.Lock()
        self._latest_annotated_jpeg: bytes | None = None
        self._latest_full_bgr: np.ndarray | None = None
        self._last_detections: list[Detection] = []
        self._viewers = 0
        self._overlay = False
        self._fps_ema = 0.0
        self._last_mono: float | None = None
        self._tracking = False

    # -- live-frame tap API (MVP-2) --
    def add_viewer(self) -> None:
        with self._frame_lock:
            self._viewers += 1

    def remove_viewer(self) -> None:
        with self._frame_lock:
            self._viewers = max(0, self._viewers - 1)

    def set_overlay(self, on: bool) -> None:
        with self._frame_lock:
            self._overlay = on

    def latest_annotated(self) -> bytes | None:
        with self._frame_lock:
            return self._latest_annotated_jpeg

    def capture_still(self) -> tuple[bytes, int, int] | None:
        with self._frame_lock:
            frame = None if self._latest_full_bgr is None else self._latest_full_bgr.copy()
        if frame is None:
            return None
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            return None
        h, w = frame.shape[:2]
        return bytes(buf), int(w), int(h)

    def stats(self) -> dict[str, object]:
        with self._frame_lock:
            return {
                "fps": round(self._fps_ema, 1),
                "tracking": self._tracking,
                "viewers": self._viewers,
            }

    def _tap_frame(self, frame_bgr, mono_ts: float) -> None:  # type: ignore[no-untyped-def]
        with self._frame_lock:
            self._latest_full_bgr = frame_bgr
            if self._last_mono is not None:
                dt = mono_ts - self._last_mono
                if dt > 0:
                    inst = 1.0 / dt
                    self._fps_ema = inst if self._fps_ema == 0 else 0.9 * self._fps_ema + 0.1 * inst
            self._last_mono = mono_ts
            want = self._viewers > 0 or self._overlay
            overlay = self._overlay
            dets = list(self._last_detections)
        if not want:
            return
        preview = frame_bgr
        if overlay and dets:
            preview = frame_bgr.copy()
            for d in dets:
                x, y, w, h = d.bbox
                cv2.rectangle(preview, (x, y), (x + w, y + h), (0, 255, 0), 2)
        ok, buf = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            with self._frame_lock:
                self._latest_annotated_jpeg = bytes(buf)

    def run_until_camera_exhausted(self) -> None:
        self._camera.open()
        try:
            prev_gray = None
            prev_full_frame = None  # BGR frame that prev_gray came from
            last_full_frame = None  # BGR of the most recent frame read
            while not self._stop.is_set():
                got = self._camera.read()
                if got is None:
                    break
                frame_bgr, ts = got
                self._tap_frame(frame_bgr, ts)
                curr_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
                if prev_gray is not None:
                    # Finalized tracks come from update() — they were last
                    # matched in PREV frame (not present in current).
                    # last_full_frame at this point is the BGR that prev_gray
                    # came from (set at end of previous iteration), so it is
                    # the last frame the vehicle was actually present in.
                    self._process_frame(prev_gray, curr_gray, last_full_frame, frame_ts=ts)
                prev_full_frame = last_full_frame
                prev_gray = curr_gray
                last_full_frame = frame_bgr
            # Source exhausted — flush any in-flight track.
            # The track's last active detection came from diff(prev_gray,
            # last_gray) — the vehicle was present in prev_full_frame (the
            # frame preceding the final one). Use prev_full_frame so the
            # event image shows the vehicle rather than a potentially-empty
            # final frame.
            flush_frame = prev_full_frame if prev_full_frame is not None else last_full_frame
            if flush_frame is not None:
                for track in self._tracker.flush():
                    self._persist_track(track, flush_frame)
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

    def _process_frame(self, prev_gray, curr_gray, prev_frame_bgr, *, frame_ts: float) -> None:  # type: ignore[no-untyped-def]
        """prev_frame_bgr is the BGR frame that prev_gray came from — the
        last frame where any finalized track was actually present.
        """
        detections = find_motion(
            prev_gray,
            curr_gray,
            min_area_px=self._settings.detector.min_area_px,
            crop=self._settings.detector.crop,
            frame_ts=frame_ts,
        )
        with self._frame_lock:
            self._last_detections = detections
            self._tracking = bool(detections)
        finalised = self._tracker.update(detections)
        for track in finalised:
            self._persist_track(track, prev_frame_bgr)

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
