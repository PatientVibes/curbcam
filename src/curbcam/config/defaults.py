"""Single source of truth for field labels and help text.

Consumed by the MVP-2 settings UI to render labels/tooltips. Keys are the
dotted path used by ``Settings`` (e.g. ``"camera.source"``). Whenever a
field is added to ``schema.py``, add a row here too — the test suite in
MVP-2 will assert every field has a label.
"""

FIELD_LABELS: dict[str, tuple[str, str]] = {
    # key: (label, help)
    "camera.source": (
        "Camera source",
        "Where curbcam reads video from. Use picamera2:0 for a Pi camera, "
        "usb:/dev/video0 for a USB webcam, an rtsp://… URL for a network camera, "
        "or file:./clip.mp4 to replay a file. Changing this restarts the capture "
        "pipeline.",
    ),
    "camera.resolution": (
        "Resolution",
        "Capture size in pixels as width x height (e.g. 1280x720). Higher resolution "
        "sees smaller or more distant objects and measures speed more precisely, "
        "but uses more CPU and memory — on a Pi, 1280x720 is a good default. Must "
        "be a size your camera actually supports.",
    ),
    "camera.fps_target": (
        "Target frame rate",
        "Frames per second the camera tries to deliver. Higher rates track fast "
        "vehicles more accurately but cost more CPU; 10-15 fps is a good balance "
        "on a Pi. Setting it higher than the camera or Pi can sustain has no "
        "effect.",
    ),
    "detector.min_area_px": (
        "Min motion area",
        "Smallest moving blob, in pixels, that counts as motion. Raise it to ignore "
        "leaves, birds, and small animals; lower it to catch smaller or more distant "
        "objects. Too high misses real vehicles; too low lets image noise trigger "
        "false events.",
    ),
    "detector.min_track_frames": (
        "Min track frames",
        "How many consecutive frames an object must be seen before it is logged as "
        "an event. Higher values reject brief flickers and noise, but may drop very "
        "fast vehicles that cross the frame in only a few frames; 3-5 is typical.",
    ),
    "detector.max_dist_px": (
        "Tracker step",
        "The farthest, in pixels, a moving object's centre may jump between frames "
        "and still be treated as the same object. Raise it for fast traffic or low "
        "frame rates so one car isn't split into two tracks; set it too high and "
        "separate vehicles get merged into one.",
    ),
    "detector.crop": (
        "Detection region",
        "Rectangle within the frame where motion is checked (set by alignment wizard)",
    ),
    "retention.max_events_per_day": (
        "Max events / day",
        "Maximum number of events kept per day. Once a day exceeds this, its oldest "
        "events are pruned to limit disk use. Increase it on a busy road if you want "
        "a fuller history.",
    ),
    "retention.max_total_disk_mb": (
        "Max total disk (MB)",
        "Upper limit, in megabytes, on the total size of stored media (snapshots and "
        "thumbnails). When the media folder grows past this, the oldest events are "
        "deleted first. Set it to comfortably fit your SD card or disk.",
    ),
    "server.units": (
        "Display units",
        "Units shown everywhere in the interface — kph or mph. This is display-only: "
        "speeds are always stored internally in km/h, so switching units never alters "
        "recorded data.",
    ),
    "server.min_event_speed_kph": (
        "Min event speed",
        "Speeds below this threshold (in km/h) are discarded before an event is "
        "saved. Raise it to ignore pedestrians and cyclists and keep only vehicles; "
        "lower it to capture slower movers. Set it too high and you'll miss real "
        "traffic.",
    ),
    "server.log_level": (
        "Log level",
        "How much detail curbcam writes to its log. INFO is the normal setting; DEBUG "
        "is verbose and useful for troubleshooting; WARNING shows only problems. More "
        "verbosity fills the log faster.",
    ),
}
