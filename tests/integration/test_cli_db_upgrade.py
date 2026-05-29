"""`db upgrade` runs alembic against the --data-dir sqlite and leaves it at
head. Runs from the repo root so alembic.ini + migrations/ resolve."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from curbcam.cli import app
from curbcam.storage.db import LATEST_MIGRATION_REVISION

runner = CliRunner()


def test_db_upgrade_brings_fresh_db_to_head(tmp_path: Path) -> None:
    result = runner.invoke(app, ["db", "upgrade", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output

    db_path = tmp_path / "curbcam.sqlite"
    assert db_path.exists()
    con = sqlite3.connect(db_path)
    try:
        ver = con.execute("SELECT version_num FROM alembic_version").fetchone()
        tables = {
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        con.close()

    assert ver is not None and ver[0] == LATEST_MIGRATION_REVISION
    assert {"events", "calibrations"} <= tables


def test_db_upgrade_is_idempotent(tmp_path: Path) -> None:
    first = runner.invoke(app, ["db", "upgrade", "--data-dir", str(tmp_path)])
    second = runner.invoke(app, ["db", "upgrade", "--data-dir", str(tmp_path)])
    assert first.exit_code == 0 and second.exit_code == 0, second.output
