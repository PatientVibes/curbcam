"""SQLAlchemy ORM models for events and calibrations.

Direct map of the schema in design spec §7.1.
"""

# `from __future__ import annotations` is intentional here (project
# convention is to omit it on Python 3.12) so the Calibration <-> Event
# back-relations can use real class references instead of string
# literals — gives mypy and IDEs something to follow on rename.
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Calibration(Base):
    __tablename__ = "calibrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_utc: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    mm_per_px_l2r: Mapped[float] = mapped_column(Float, nullable=False)
    mm_per_px_r2l: Mapped[float] = mapped_column(Float, nullable=False)
    reference_distance_mm: Mapped[float] = mapped_column(Float, nullable=False)
    reference_points_json: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    events: Mapped[list[Event]] = relationship(back_populates="calibration")

    __table_args__ = (
        Index(
            "one_active_calibration",
            "active",
            unique=True,
            sqlite_where=text("active = 1"),
        ),
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts_utc: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    speed_kph: Mapped[float] = mapped_column(Float, nullable=False)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    frame_count: Mapped[int] = mapped_column(Integer, nullable=False)
    track_len_px: Mapped[int] = mapped_column(Integer, nullable=False)
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    thumb_path: Mapped[str] = mapped_column(Text, nullable=False)
    calibration_id: Mapped[int | None] = mapped_column(ForeignKey("calibrations.id"), nullable=True)

    calibration: Mapped[Calibration | None] = relationship(back_populates="events")

    __table_args__ = (Index("events_ts", "ts_utc"),)
