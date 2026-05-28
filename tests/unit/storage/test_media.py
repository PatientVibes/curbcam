import datetime as dt
from pathlib import Path

import cv2
import numpy as np

from curbcam.storage.media import MediaWriter


def test_save_event_image_writes_full_and_thumb(tmp_path: Path) -> None:
    writer = MediaWriter(media_root=tmp_path)
    frame = np.full((480, 640, 3), fill_value=128, dtype=np.uint8)
    ts = dt.datetime(2026, 5, 28, 14, 30, 5)

    full_rel, thumb_rel = writer.save_event_image(
        frame=frame, event_id=42, ts_utc=ts, speed_kph=37.5, direction="L2R"
    )

    full_abs = tmp_path / full_rel
    thumb_abs = tmp_path / thumb_rel
    assert full_abs.exists()
    assert thumb_abs.exists()
    assert full_rel == "events/2026/05/28/event_42.jpg"
    assert thumb_rel == "thumbs/2026/05/28/event_42.jpg"

    full = cv2.imread(str(full_abs))
    thumb = cv2.imread(str(thumb_abs))
    assert full.shape == (480, 640, 3)
    assert thumb.shape[1] == 320  # default thumb width
