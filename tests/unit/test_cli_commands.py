"""Unit tests for the CLI commands via typer's CliRunner (no subprocess).

These hit the actual command functions directly, giving coverage to cli.py
without spawning child processes.
"""

from pathlib import Path

from typer.testing import CliRunner

from curbcam.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# db init
# ---------------------------------------------------------------------------


def test_db_init_creates_schema(tmp_path: Path) -> None:
    result = runner.invoke(app, ["db", "init", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "Schema initialised" in result.output
    db_path = tmp_path / "curbcam.sqlite"
    assert db_path.exists()


def test_db_init_is_idempotent(tmp_path: Path) -> None:
    runner.invoke(app, ["db", "init", "--data-dir", str(tmp_path)])
    result = runner.invoke(app, ["db", "init", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# calibrate
# ---------------------------------------------------------------------------


def test_calibrate_writes_active_calibration(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "calibrate",
            "--mm-per-px-l2r",
            "12.5",
            "--mm-per-px-r2l",
            "11.0",
            "--reference-distance-mm",
            "500",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Active calibration #" in result.output


def test_calibrate_with_notes(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "calibrate",
            "--mm-per-px-l2r",
            "10.0",
            "--mm-per-px-r2l",
            "10.0",
            "--reference-distance-mm",
            "400",
            "--notes",
            "test calibration",
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output


def test_calibrate_missing_required_arg_exits_nonzero(tmp_path: Path) -> None:
    """Missing a required option should produce a non-zero exit code."""
    result = runner.invoke(
        app,
        [
            "calibrate",
            "--mm-per-px-l2r",
            "10.0",
            # missing --mm-per-px-r2l and --reference-distance-mm
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# detect — quick path via --once with a file source
# ---------------------------------------------------------------------------


def test_detect_once_with_file_source(tmp_path: Path) -> None:
    """detect --once with a single-frame file source should exit 0."""
    import cv2
    import numpy as np

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    # Write a single blank frame so FileReplaySource exhausts immediately.
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.imwrite(str(run_dir / "0000.jpg"), frame)

    data_dir = tmp_path / "data"
    media_dir = tmp_path / "media"

    result = runner.invoke(
        app,
        [
            "detect",
            "--config",
            str(tmp_path / "curbcam.yaml"),
            "--data-dir",
            str(data_dir),
            "--media-dir",
            str(media_dir),
            "--camera",
            f"file:{run_dir}",
            "--min-event-speed-kph",
            "999",  # nothing will clear this threshold
            "--once",
        ],
    )
    assert result.exit_code == 0, result.output
