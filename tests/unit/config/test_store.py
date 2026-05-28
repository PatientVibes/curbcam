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


def test_env_var_overrides_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CURBCAM_CAMERA__SOURCE", "rtsp://override-host/stream")
    path = tmp_path / "curbcam.yaml"
    store = ConfigStore(path)
    s = store.load()
    assert s.camera.source == "rtsp://override-host/stream"
