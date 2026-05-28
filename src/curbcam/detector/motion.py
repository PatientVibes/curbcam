"""Frame-diff motion detection.

Algorithm: absolute difference between consecutive grayscale frames →
Gaussian blur → binary threshold → dilate → contour extraction. Contours
below ``min_area_px`` are dropped. Optionally clipped to a crop rectangle
in source-image coordinates.

Returned bounding boxes and centroids are always in SOURCE coordinates
(crop is applied internally and translated back).

``frame_ts`` MUST be the capture timestamp of ``curr_gray`` (typically
the monotonic seconds returned by ``camera.read()``). It is propagated
verbatim into every returned Detection so speed calculations downstream
use real elapsed wall-clock between captures, not detector compute time.
"""

import cv2
import numpy as np

from curbcam.detector.types import CropRect, Detection


def find_motion(
    prev_gray: np.ndarray,
    curr_gray: np.ndarray,
    *,
    min_area_px: int,
    crop: CropRect | None,
    frame_ts: float,
) -> list[Detection]:
    """Return Detections for connected motion blobs above ``min_area_px``."""
    if crop is not None:
        x0, y0, x1, y1 = crop
        prev_view = prev_gray[y0:y1, x0:x1]
        curr_view = curr_gray[y0:y1, x0:x1]
    else:
        x0, y0 = 0, 0
        prev_view = prev_gray
        curr_view = curr_gray

    diff = cv2.absdiff(prev_view, curr_view)
    blurred = cv2.GaussianBlur(diff, (5, 5), 0)
    _, thresh = cv2.threshold(blurred, 25, 255, cv2.THRESH_BINARY)
    kernel = np.ones((3, 3), dtype=np.uint8)
    dilated = cv2.dilate(thresh, kernel, iterations=2)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    out: list[Detection] = []
    for c in contours:
        area = int(cv2.contourArea(c))
        if area < min_area_px:
            continue
        x, y, w, h = cv2.boundingRect(c)
        # Translate back to source coordinates.
        src_x, src_y = x + x0, y + y0
        cx, cy = src_x + w // 2, src_y + h // 2
        out.append(
            Detection(
                bbox=(src_x, src_y, w, h),
                centroid=(cx, cy),
                area_px=area,
                frame_ts=frame_ts,
            )
        )
    return out
