import subprocess
import sys
from pathlib import Path

import pytest

from tests.integration.fixtures.synthetic_run import write_synthetic_run


@pytest.mark.timeout(60)
def test_cli_detect_writes_events_to_sqlite(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    write_synthetic_run(run_dir, frames=10, step_px=40)

    data_dir = tmp_path / "data"
    media_dir = tmp_path / "media"
    config_path = tmp_path / "curbcam.yaml"

    # Seed a calibration via the CLI itself (single-command setup).
    result = subprocess.run(
        [
            sys.executable, "-m", "curbcam.cli", "calibrate",
            "--mm-per-px-l2r", "10.0",
            "--mm-per-px-r2l", "10.0",
            "--reference-distance-mm", "400",
            "--data-dir", str(data_dir),
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    # Run the detect command against the file source.
    result = subprocess.run(
        [
            sys.executable, "-m", "curbcam.cli", "detect",
            "--config", str(config_path),
            "--data-dir", str(data_dir),
            "--media-dir", str(media_dir),
            "--camera", f"file:{run_dir}",
            "--min-event-speed-kph", "0",
            "--once",
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    # Assert at least one event was written to the DB.
    import sqlite3
    db_path = data_dir / "curbcam.sqlite"
    assert db_path.exists()
    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert count >= 1
    finally:
        conn.close()
