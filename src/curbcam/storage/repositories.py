"""Thin repository wrappers over the ORM.

Why: keep callers (the pipeline runner, the API routes) free from
SQLAlchemy session boilerplate, and make the active-calibration
invariant a single function call.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

from sqlalchemy import and_, or_, update

from curbcam.localtime import to_local
from curbcam.storage.db import Database
from curbcam.storage.models import Calibration, Event


@dataclass
class EventFilter:
    start: dt.datetime | None = None
    end: dt.datetime | None = None
    min_speed_kph: float | None = None
    max_speed_kph: float | None = None
    direction: str | None = None


@dataclass
class ReportSummary:
    count: int
    median_kph: float
    p85_kph: float
    max_kph: float


def _percentile(sorted_vals: list[float], pct: float) -> float:
    """Linear-interpolated percentile (numpy 'linear' method)."""
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return sorted_vals[int(k)]
    return sorted_vals[lo] * (hi - k) + sorted_vals[hi] * (k - lo)


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

    def query(
        self,
        f: EventFilter,
        *,
        cursor: tuple[dt.datetime, int] | None = None,
        limit: int = 50,
    ) -> list[Event]:
        """Newest-first, keyset-paginated on (ts_utc, id)."""
        with self._db.session() as s:
            q = s.query(Event)
            if f.start is not None:
                q = q.filter(Event.ts_utc >= f.start)
            if f.end is not None:
                q = q.filter(Event.ts_utc <= f.end)
            if f.min_speed_kph is not None:
                q = q.filter(Event.speed_kph >= f.min_speed_kph)
            if f.max_speed_kph is not None:
                q = q.filter(Event.speed_kph <= f.max_speed_kph)
            if f.direction is not None:
                q = q.filter(Event.direction == f.direction)
            if cursor is not None:
                cts, cid = cursor
                q = q.filter(or_(Event.ts_utc < cts, and_(Event.ts_utc == cts, Event.id < cid)))
            return q.order_by(Event.ts_utc.desc(), Event.id.desc()).limit(limit).all()

    def delete_older_than(self, cutoff: dt.datetime) -> list[str]:
        """Delete event rows older than ``cutoff``; return the relative media
        paths (image + thumb) of the deleted rows so the caller can unlink the
        files. Rows are fetched (rather than bulk-deleted) precisely so the
        media paths can be returned — the privacy "delete old events" button
        must remove the JPEGs, not just the DB rows.
        """
        with self._db.session() as s:
            rows = s.query(Event).filter(Event.ts_utc < cutoff).all()
            paths = [p for r in rows for p in (r.image_path, r.thumb_path) if p]
            for r in rows:
                s.delete(r)
            s.commit()
            return paths

    def speeds_since(self, start: dt.datetime | None, direction: str | None = None) -> list[float]:
        """Sorted kph speeds in the window. Public so the reports view-model can
        bucket the histogram in display units (mph/kph) rather than raw kph."""
        with self._db.session() as s:
            q = s.query(Event.speed_kph)
            if start is not None:
                q = q.filter(Event.ts_utc >= start)
            if direction is not None:
                q = q.filter(Event.direction == direction)
            return sorted(float(r[0]) for r in q.all())

    def summary(self, start: dt.datetime | None) -> ReportSummary:
        speeds = self.speeds_since(start)
        if not speeds:
            return ReportSummary(0, 0.0, 0.0, 0.0)
        return ReportSummary(
            count=len(speeds),
            median_kph=_percentile(speeds, 50),
            p85_kph=_percentile(speeds, 85),
            max_kph=speeds[-1],
        )

    def _timestamps_since(self, start: dt.datetime | None) -> list[dt.datetime]:
        with self._db.session() as s:
            q = s.query(Event.ts_utc)
            if start is not None:
                q = q.filter(Event.ts_utc >= start)
            return [r[0] for r in q.all()]

    def by_hour(self, start: dt.datetime | None, tz: dt.tzinfo = dt.UTC) -> list[int]:
        # Bucket by LOCAL hour-of-day. SQLite strftime can't apply an IANA zone
        # (DST-correct), so convert each timestamp in Python via ``tz``.
        out = [0] * 24
        for tsu in self._timestamps_since(start):
            out[to_local(tsu, tz).hour] += 1
        return out

    def daily_counts(
        self, start: dt.datetime | None, tz: dt.tzinfo = dt.UTC
    ) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for tsu in self._timestamps_since(start):
            key = to_local(tsu, tz).date().isoformat()
            counts[key] = counts.get(key, 0) + 1
        return sorted(counts.items())

    def by_direction(self, start: dt.datetime | None) -> dict[str, tuple[int, float]]:
        out: dict[str, tuple[int, float]] = {}
        for direction in ("L2R", "R2L"):
            speeds = self.speeds_since(start, direction)
            out[direction] = (len(speeds), _percentile(speeds, 50) if speeds else 0.0)
        return out
