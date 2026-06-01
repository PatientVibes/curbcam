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
    "server.timezone": (
        "Timezone",
        "Your local timezone as an IANA name, e.g. America/New_York or "
        "Europe/London. Used for the Reports page (hour-of-day, daily totals, the "
        "Today window) and the time shown in alerts. Leave blank to use UTC. The "
        "live event feed always shows your browser's local time.",
    ),
    "server.log_level": (
        "Log level",
        "How much detail curbcam writes to its log. INFO is the normal setting; DEBUG "
        "is verbose and useful for troubleshooting; WARNING shows only problems. More "
        "verbosity fills the log faster.",
    ),
    "alerts.enabled": (
        "Enable alerts",
        "Master switch. When off, no channel fires regardless of its own setting.",
    ),
    "alerts.min_speed_kph": (
        "Alert speed (km/h)",
        "Only vehicles at or above this speed (in km/h) trigger an alert. Independent "
        "of the recording threshold; usually set higher.",
    ),
    "alerts.base_url": (
        "Site URL",
        "Base URL used for the click-through link in alerts, e.g. "
        "http://curbcam.local:8080. Leave blank to send no link.",
    ),
    "alerts.ntfy_enabled": ("ntfy: enable", "Send alerts to an ntfy topic (phone push)."),
    "alerts.ntfy_server": ("ntfy: server", "ntfy server base URL. Default https://ntfy.sh."),
    "alerts.ntfy_topic": (
        "ntfy: topic",
        "The ntfy topic to publish to (required). WARNING: on the public ntfy.sh "
        "server, anyone who knows the topic name can read your alerts — choose a "
        "long, random, unguessable name (e.g. curbcam-7f3k9q2x), or run your own "
        "ntfy server.",
    ),
    "alerts.ntfy_cooldown_s": (
        "ntfy: cooldown (s)",
        "Minimum seconds between ntfy alerts. 0 sends one per qualifying event.",
    ),
    "alerts.webhook_enabled": ("Webhook: enable", "POST a JSON body to a URL of your choice."),
    "alerts.webhook_url": ("Webhook: URL", "Destination URL for the JSON POST. Required."),
    "alerts.webhook_cooldown_s": (
        "Webhook: cooldown (s)",
        "Minimum seconds between webhook posts. 0 sends one per qualifying event.",
    ),
    "alerts.mqtt_enabled": ("MQTT: enable", "Publish a JSON body to an MQTT broker."),
    "alerts.mqtt_host": ("MQTT: host", "Broker hostname or IP. Required for MQTT."),
    "alerts.mqtt_port": ("MQTT: port", "Broker port. Default 1883."),
    "alerts.mqtt_topic": ("MQTT: topic", "Topic to publish to. Default curbcam/events."),
    "alerts.mqtt_username": ("MQTT: username", "Broker username (optional)."),
    "alerts.mqtt_password": ("MQTT: password", "Broker password (optional)."),
    "alerts.mqtt_cooldown_s": (
        "MQTT: cooldown (s)",
        "Minimum seconds between MQTT publishes. 0 (default) publishes every "
        "qualifying event — the right setting for Home Assistant.",
    ),
}
