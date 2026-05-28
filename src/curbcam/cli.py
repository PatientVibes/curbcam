"""curbcam command-line interface.

Subcommands:
    curbcam detect      Run the pipeline against a configured camera.
    curbcam calibrate   Insert a new active calibration row directly.
    curbcam db init     Create/upgrade the SQLite schema.
"""

import logging
from pathlib import Path

import typer

from curbcam.camera.factory import camera_from_source
from curbcam.config.store import ConfigStore
from curbcam.pipeline.events import EventBus
from curbcam.pipeline.runner import PipelineRunner
from curbcam.storage.db import Database
from curbcam.storage.media import MediaWriter
from curbcam.storage.models import Base
from curbcam.storage.repositories import CalibrationRepo

app = typer.Typer(help="curbcam — speed camera CLI", no_args_is_help=True)


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-5s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


@app.command()
def detect(
    config: Path = typer.Option(Path("curbcam.yaml"), help="Path to YAML config"),
    data_dir: Path = typer.Option(Path("./data"), help="Directory for SQLite DB"),
    media_dir: Path = typer.Option(Path("./media"), help="Directory for event JPEGs"),
    camera: str | None = typer.Option(None, help="Override camera source string"),
    min_event_speed_kph: float | None = typer.Option(None),
    once: bool = typer.Option(False, help="Run until camera exhausts, then exit"),
) -> None:
    """Run the pipeline."""
    store = ConfigStore(config)
    settings = store.load()
    if camera is not None:
        settings = settings.model_copy(update={
            "camera": settings.camera.model_copy(update={"source": camera}),
        })
    if min_event_speed_kph is not None:
        settings = settings.model_copy(update={
            "server": settings.server.model_copy(
                update={"min_event_speed_kph": min_event_speed_kph}
            ),
        })

    _setup_logging(settings.server.log_level)

    db = Database.for_sqlite_path(data_dir / "curbcam.sqlite")
    Base.metadata.create_all(db.engine)   # idempotent; alembic-managed in prod

    cam = camera_from_source(
        settings.camera.source,
        resolution=settings.camera.resolution,
        fps_target=settings.camera.fps_target,
        loop=not once,
    )

    runner = PipelineRunner(
        camera=cam,
        db=db,
        calibration_repo=CalibrationRepo(db),
        media=MediaWriter(media_dir),
        bus=EventBus(),
        settings=settings,
    )

    if once:
        runner.run_until_camera_exhausted()
        return

    thread = runner.run_in_background_thread()
    try:
        thread.join()
    except KeyboardInterrupt:
        runner.stop()


@app.command()
def calibrate(
    mm_per_px_l2r: float = typer.Option(..., "--mm-per-px-l2r"),
    mm_per_px_r2l: float = typer.Option(..., "--mm-per-px-r2l"),
    reference_distance_mm: float = typer.Option(..., "--reference-distance-mm"),
    notes: str | None = typer.Option(None),
    data_dir: Path = typer.Option(Path("./data")),
) -> None:
    """Write a new active calibration directly (CLI bootstrap before MVP-2 UI)."""
    db = Database.for_sqlite_path(data_dir / "curbcam.sqlite")
    Base.metadata.create_all(db.engine)
    repo = CalibrationRepo(db)
    cal = repo.save_new_active(
        mm_per_px_l2r=mm_per_px_l2r,
        mm_per_px_r2l=mm_per_px_r2l,
        reference_distance_mm=reference_distance_mm,
        reference_points_json="[]",
        notes=notes,
    )
    typer.echo(f"Active calibration #{cal.id} written.")


db_app = typer.Typer(help="Database admin")
app.add_typer(db_app, name="db")


@db_app.command("init")
def db_init(data_dir: Path = typer.Option(Path("./data"))) -> None:
    """Create the SQLite schema (idempotent)."""
    db = Database.for_sqlite_path(data_dir / "curbcam.sqlite")
    Base.metadata.create_all(db.engine)
    typer.echo(f"Schema initialised at {data_dir / 'curbcam.sqlite'}")


def main() -> None:   # pragma: no cover
    app()


if __name__ == "__main__":   # pragma: no cover
    main()
