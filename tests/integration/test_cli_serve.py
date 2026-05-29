"""serve must construct the app + supervisor and hand off to uvicorn.

We patch uvicorn.run so the test doesn't actually bind a socket.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import curbcam.cli as cli_mod
from curbcam.cli import app

runner = CliRunner()


def test_serve_builds_app_and_calls_uvicorn(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict = {}

    def fake_run(app_obj, host: str, port: int, **kw) -> None:  # type: ignore[no-untyped-def]
        captured["app"] = app_obj
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr(cli_mod.uvicorn, "run", fake_run)

    result = runner.invoke(
        app,
        [
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            "9111",
            "--config",
            str(tmp_path / "curbcam.yaml"),
            "--data-dir",
            str(tmp_path / "data"),
            "--media-dir",
            str(tmp_path / "media"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9111
    assert captured["app"].__class__.__name__ == "FastAPI"
