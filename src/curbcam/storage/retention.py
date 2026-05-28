"""Single retention sweeper.

Two policies enforced (centralised — design spec §7.2):
1. ``max_events_per_day``: per-day count cap.
2. ``max_total_disk_mb``: total media-folder size cap (oldest events purged first).

The sweeper deletes the DB row AND the JPEG + thumbnail. It is safe to
run repeatedly (no-op if everything is under cap). Returns count of
events deleted.
"""

import logging
from pathlib import Path

from sqlalchemy import func

from curbcam.storage.db import Database
from curbcam.storage.models import Event

log = logging.getLogger(__name__)


class RetentionSweeper:
    def __init__(
        self,
        *,
        db: Database,
        media_root: Path,
        max_events_per_day: int,
        max_total_disk_mb: int,
    ) -> None:
        self._db = db
        self._media_root = media_root
        self._max_per_day = max_events_per_day
        self._max_disk_bytes = max_total_disk_mb * 1024 * 1024

    def sweep(self) -> int:
        deleted = 0
        deleted += self._enforce_per_day_cap()
        deleted += self._enforce_disk_cap()
        return deleted

    def _enforce_per_day_cap(self) -> int:
        deleted = 0
        with self._db.session() as s:
            day_counts = (
                s.query(func.date(Event.ts_utc).label("day"), func.count(Event.id))
                .group_by("day")
                .having(func.count(Event.id) > self._max_per_day)
                .all()
            )
            for day, _count in day_counts:
                victims = (
                    s.query(Event)
                    .filter(func.date(Event.ts_utc) == day)
                    .order_by(Event.ts_utc.asc())
                    .all()
                )
                to_delete = victims[: len(victims) - self._max_per_day]
                for ev in to_delete:
                    if not self._delete_files(ev):
                        # Files survived (permission, read-only fs, etc.) —
                        # keep the row so the file is not orphaned.
                        continue
                    s.delete(ev)
                    deleted += 1
            s.commit()
        return deleted

    def _enforce_disk_cap(self) -> int:
        deleted = 0
        with self._db.session() as s:
            while True:
                total = self._total_media_bytes()
                if total <= self._max_disk_bytes:
                    break
                oldest = s.query(Event).order_by(Event.ts_utc.asc()).first()
                if oldest is None:
                    break
                if not self._delete_files(oldest):
                    # Cannot shrink disk further without orphaning rows;
                    # abort so we don't infinite-loop on the same event.
                    log.warning(
                        "Disk-cap sweep aborted: cannot delete files for "
                        "oldest event (still over cap)"
                    )
                    break
                s.delete(oldest)
                s.commit()
                deleted += 1
        return deleted

    def _total_media_bytes(self) -> int:
        total = 0
        for path in self._media_root.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
        return total

    def _delete_files(self, ev: Event) -> bool:
        """Delete the event's image + thumbnail. Returns True if all targeted
        files are gone after the call (already-absent counts as success);
        False if any unlink raised OSError so the caller can leave the DB
        row in place rather than orphaning files on disk.
        """
        ok = True
        for rel in (ev.image_path, ev.thumb_path):
            if not rel:
                continue
            p = self._media_root / rel
            try:
                p.unlink(missing_ok=True)
            except OSError:
                log.exception("Failed to delete %s; leaving event row in place", p)
                ok = False
        return ok
