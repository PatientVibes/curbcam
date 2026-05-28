from pathlib import Path

import pytest

from curbcam.config.schema import Settings
from curbcam.config.store import ConfigStore


def test_load_creates_file_with_defaults_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "curbcam.yaml"
    store = ConfigStore(path)
    s = store.load()
    assert isinstance(s, Settings)
    assert path.exists()


def test_save_then_load_round_trips_values(tmp_path: Path) -> None:
    path = tmp_path / "curbcam.yaml"
    store = ConfigStore(path)
    s = store.load()
    s = s.model_copy(
        update={
            "server": s.server.model_copy(update={"units": "mph", "min_event_speed_kph": 10.0}),
        }
    )
    store.save(s)

    reloaded = ConfigStore(path).load()
    assert reloaded.server.units == "mph"
    assert reloaded.server.min_event_speed_kph == 10.0


def test_env_var_overrides_yaml_when_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """File-missing path: load() creates defaults, env overlay applies."""
    monkeypatch.setenv("CURBCAM_CAMERA__SOURCE", "rtsp://override-host/stream")
    path = tmp_path / "curbcam.yaml"
    store = ConfigStore(path)
    s = store.load()
    assert s.camera.source == "rtsp://override-host/stream"


def test_env_var_overrides_yaml_when_file_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Existing-file path: env still wins over the persisted YAML value."""
    path = tmp_path / "curbcam.yaml"
    # First write a YAML with a specific (non-default) camera source.
    initial = Settings()
    initial = initial.model_copy(
        update={
            "camera": initial.camera.model_copy(update={"source": "usb:/dev/video0"}),
        }
    )
    ConfigStore(path).save(initial)

    # Now set an env var and re-load through a fresh store.
    monkeypatch.setenv("CURBCAM_CAMERA__SOURCE", "rtsp://override-host/stream")
    reloaded = ConfigStore(path).load()

    assert reloaded.camera.source == "rtsp://override-host/stream", (
        "env var must override the persisted YAML value on subsequent loads, "
        "not just on first-run when the file is missing"
    )


def test_load_does_not_persist_env_overrides_on_first_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """First-run YAML write must not leak env-only credentials to disk.

    The returned Settings should still reflect the env overlay (so the
    runner uses the correct camera source), but the YAML file itself
    contains only true defaults — env-vars stay out of the persisted
    config.
    """
    monkeypatch.setenv("CURBCAM_CAMERA__SOURCE", "rtsp://user:pw@cam.local/stream")
    path = tmp_path / "curbcam.yaml"
    store = ConfigStore(path)

    s = store.load()
    # Returned settings DO have the env value applied (runtime contract).
    assert s.camera.source == "rtsp://user:pw@cam.local/stream"

    # But the YAML on disk holds only the default, not the credentials.
    monkeypatch.delenv("CURBCAM_CAMERA__SOURCE")
    on_disk = ConfigStore(path).load()
    assert on_disk.camera.source == "picamera2:0", (
        "first-run write must not persist env-overlaid values; otherwise "
        "RTSP credentials passed via env vars leak into the on-disk YAML"
    )
