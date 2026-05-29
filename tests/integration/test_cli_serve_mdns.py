"""serve must start/stop the mDNS publisher around uvicorn and print the
banner when mDNS is enabled, and skip the publisher entirely with --no-mdns.
uvicorn.run is patched so no socket is bound."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from typer.testing import CliRunner

import curbcam.cli as cli_mod
from curbcam.cli import app

runner = CliRunner()


class _FakePublisher:
    instances: ClassVar[list[_FakePublisher]] = []

    def __init__(self, ip: str, port: int) -> None:
        self.ip = ip
        self.port = port
        self.started = 0
        self.stopped = 0
        _FakePublisher.instances.append(self)

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1


def _patch(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _FakePublisher.instances.clear()
    monkeypatch.setattr(cli_mod.uvicorn, "run", lambda *a, **k: None)
    monkeypatch.setattr(cli_mod, "MDNSPublisher", _FakePublisher)
    monkeypatch.setattr(cli_mod, "detect_lan_ip", lambda: "10.0.0.5")


def test_serve_starts_and_stops_publisher_and_prints_banner(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _patch(monkeypatch)
    result = runner.invoke(
        app,
        [
            "serve",
            "--port",
            "8080",
            "--config",
            str(tmp_path / "c.yaml"),
            "--data-dir",
            str(tmp_path / "data"),
            "--media-dir",
            str(tmp_path / "media"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert len(_FakePublisher.instances) == 1
    pub = _FakePublisher.instances[0]
    assert pub.started == 1 and pub.stopped == 1
    assert pub.ip == "10.0.0.5" and pub.port == 8080
    assert "curbcam.local:8080" in result.output
    assert "10.0.0.5:8080" in result.output


def test_serve_no_mdns_skips_publisher(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _patch(monkeypatch)
    result = runner.invoke(
        app,
        [
            "serve",
            "--no-mdns",
            "--config",
            str(tmp_path / "c.yaml"),
            "--data-dir",
            str(tmp_path / "data"),
            "--media-dir",
            str(tmp_path / "media"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert _FakePublisher.instances == []


def test_serve_stops_publisher_even_when_uvicorn_raises(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _patch(monkeypatch)

    def _boom(*_a, **_k) -> None:
        raise RuntimeError("bind failed")

    monkeypatch.setattr(cli_mod.uvicorn, "run", _boom)
    result = runner.invoke(
        app,
        [
            "serve",
            "--config",
            str(tmp_path / "c.yaml"),
            "--data-dir",
            str(tmp_path / "data"),
            "--media-dir",
            str(tmp_path / "media"),
        ],
    )
    assert result.exit_code != 0
    assert len(_FakePublisher.instances) == 1
    assert _FakePublisher.instances[0].stopped == 1
