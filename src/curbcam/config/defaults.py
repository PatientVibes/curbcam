"""Single source of truth for field labels and help text.

Consumed by the MVP-2 settings UI to render labels/tooltips. Keys are the
dotted path used by ``Settings`` (e.g. ``"camera.source"``). Whenever a
field is added to ``schema.py``, add a row here too — the test suite in
MVP-2 will assert every field has a label.
"""

FIELD_LABELS: dict[str, tuple[str, str]] = {
    # key: (label, help)
    "camera.source": ("Camera source", "picamera2:0 | usb:/dev/video0 | rtsp://... | file:./path"),
    "camera.resolution": ("Resolution", "Width x height in pixels"),
    "camera.fps_target": (
        "Target frame rate",
        "Frames per second the camera should try to deliver",
    ),
    "detector.min_area_px": ("Min motion area", "Ignore moving objects smaller than this (pixels)"),
    "detector.min_track_frames": (
        "Min track frames",
        "An object must be seen this many frames to count as an event",
    ),
    "detector.max_dist_px": (
        "Tracker step",
        "Maximum per-frame centroid movement that still counts as the same object",
    ),
    "detector.crop": (
        "Detection region",
        "Rectangle within the frame where motion is checked (set by alignment wizard)",
    ),
    "retention.max_events_per_day": (
        "Max events / day",
        "Cap on how many events to keep per day before pruning",
    ),
    "retention.max_total_disk_mb": (
        "Max total disk (MB)",
        "Total size of media/ before old events are pruned",
    ),
    "server.units": ("Display units", "kph or mph for everything user-facing"),
    "server.min_event_speed_kph": (
        "Min event speed",
        "Events slower than this are dropped before storage",
    ),
    "server.log_level": ("Log level", "DEBUG / INFO / WARNING"),
}
