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
