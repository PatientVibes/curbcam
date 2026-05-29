from pathlib import Path

from curbcam.config.store import ConfigStore


def test_load_raw_returns_plain_yaml_without_env(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "curbcam.yaml"
    store = ConfigStore(path)
    store.load()  # writes defaults
    monkeypatch.setenv("CURBCAM_CAMERA__SOURCE", "rtsp://env-host/s")
    raw = store.load_raw()
    # Raw YAML reflects the file, NOT the env override.
    assert raw["camera"]["source"] != "rtsp://env-host/s"


def test_save_raw_round_trips(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "curbcam.yaml"
    store = ConfigStore(path)
    store.load()
    raw = store.load_raw()
    raw["server"]["units"] = "mph"
    store.save_raw(raw)
    assert store.load_raw()["server"]["units"] == "mph"
