"""Thin repository wrappers over the ORM.

Why: keep callers (the pipeline runner, the API routes) free from
SQLAlchemy session boilerplate, and make the active-calibration
invariant a single function call.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import update

from curbcam.storage.db import Database
from curbcam.storage.models import Calibration, Event


class CalibrationRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def save_new_active(
        self,
        mm_per_px_l2r: float,
        mm_per_px_r2l: float,
        reference_distance_mm: float,
        reference_points_json: str,
        notes: str | None = None,
    ) -> Calibration:
        """Insert a new calibration row and mark it as the only active one."""
        with self._db.session() as s:
            # Deactivate any currently-active row(s).
            s.execute(update(Calibration).where(Calibration.active.is_(True)).values(active=False))
            cal = Calibration(
                created_utc=dt.datetime.now(dt.UTC).replace(tzinfo=None),
                mm_per_px_l2r=mm_per_px_l2r,
                mm_per_px_r2l=mm_per_px_r2l,
                reference_distance_mm=reference_distance_mm,
                reference_points_json=reference_points_json,
                active=True,
                notes=notes,
            )
            s.add(cal)
            s.commit()
            s.refresh(cal)
            return cal

    def get_active(self) -> Calibration | None:
        with self._db.session() as s:
            return s.query(Calibration).filter(Calibration.active.is_(True)).one_or_none()


class EventRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def save(
        self,
        *,
        ts_utc: dt.datetime,
        speed_kph: float,
        direction: str,
        frame_count: int,
        track_len_px: int,
        image_path: str,
        thumb_path: str,
        calibration_id: int | None,
    ) -> Event:
        with self._db.session() as s:
            event = Event(
                ts_utc=ts_utc,
                speed_kph=speed_kph,
                direction=direction,
                frame_count=frame_count,
                track_len_px=track_len_px,
                image_path=image_path,
                thumb_path=thumb_path,
                calibration_id=calibration_id,
            )
            s.add(event)
            s.commit()
            s.refresh(event)
            return event

    def list_recent(self, limit: int = 20) -> list[Event]:
        with self._db.session() as s:
            return s.query(Event).order_by(Event.ts_utc.desc()).limit(limit).all()
