"""Write event images and thumbnails to the media root.

Layout (matches design spec §7.2):
    media/events/YYYY/MM/DD/event_<id>.jpg
    media/thumbs/YYYY/MM/DD/event_<id>.jpg

Annotation: the full image and thumbnail both get a small bottom-strip
overlay with timestamp + speed + direction arrow. Bounding boxes etc.
are NOT persisted (see design spec §7.2).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import cv2
import numpy as np

_THUMB_WIDTH = 320
_JPEG_QUALITY = 85


class MediaWriter:
    def __init__(self, media_root: Path) -> None:
        self._root = media_root

    def save_event_image(
        self,
        *,
        frame: np.ndarray,
        event_id: int,
        ts_utc: dt.datetime,
        speed_kph: float,
        direction: str,
    ) -> tuple[str, str]:
        """Write full + thumb, return their paths RELATIVE to the media root."""
        date_suffix = ts_utc.strftime("%Y/%m/%d")
        rel_full = f"events/{date_suffix}/event_{event_id}.jpg"
        rel_thumb = f"thumbs/{date_suffix}/event_{event_id}.jpg"

        annotated = _annotate(frame, ts_utc=ts_utc, speed_kph=speed_kph, direction=direction)

        full_abs = self._root / rel_full
        thumb_abs = self._root / rel_thumb
        full_abs.parent.mkdir(parents=True, exist_ok=True)
        thumb_abs.parent.mkdir(parents=True, exist_ok=True)

        cv2.imwrite(str(full_abs), annotated, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY])

        h, w = annotated.shape[:2]
        thumb_h = int(h * (_THUMB_WIDTH / w))
        thumb = cv2.resize(annotated, (_THUMB_WIDTH, thumb_h), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(thumb_abs), thumb, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY])

        return rel_full, rel_thumb


def _annotate(
    frame: np.ndarray,
    *,
    ts_utc: dt.datetime,
    speed_kph: float,
    direction: str,
) -> np.ndarray:
    out = frame.copy()
    h, w = out.shape[:2]
    strip_h = 30
    # Dark strip across the bottom for legibility.
    cv2.rectangle(out, (0, h - strip_h), (w, h), (0, 0, 0), thickness=-1)
    # ASCII direction marker: cv2.putText with the default Hershey font
    # cannot render Unicode arrows (renders as "?"). ">>" and "<<" are
    # visually clear and font-safe everywhere OpenCV runs.
    arrow = ">>" if direction == "L2R" else "<<"
    text = f"{ts_utc.strftime('%Y-%m-%d %H:%M:%S')}  {speed_kph:5.1f} kph  {arrow}"
    cv2.putText(
        out,
        text,
        (8, h - 8),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return out
