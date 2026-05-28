"""Pydantic models for curbcam settings.

Persisted to YAML on disk. Field labels and help text live in
``defaults.py`` so the settings UI in MVP-2 reads from a single source
of truth.
"""

from typing import Literal

from pydantic import BaseModel, Field, PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict

from curbcam.detector.types import CropRect


class CameraSettings(BaseModel):
    source: str = "picamera2:0"
    resolution: tuple[PositiveInt, PositiveInt] = (1280, 720)
    fps_target: float = Field(default=15.0, gt=0)


class DetectorSettings(BaseModel):
    min_area_px: PositiveInt = 800
    min_track_frames: PositiveInt = 5
    max_dist_px: PositiveInt = 100
    crop: CropRect | None = None


class RetentionSettings(BaseModel):
    max_events_per_day: PositiveInt = 500
    max_total_disk_mb: PositiveInt = 5000


class ServerSettings(BaseModel):
    units: Literal["kph", "mph"] = "kph"
    min_event_speed_kph: float = Field(default=5.0, ge=0)
    log_level: Literal["DEBUG", "INFO", "WARNING"] = "INFO"


class Settings(BaseSettings):
    """Root settings model. Env vars override fields, e.g.
    ``CURBCAM_CAMERA__SOURCE=rtsp://...`` overrides ``camera.source``.
    """

    model_config = SettingsConfigDict(
        env_prefix="CURBCAM_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    camera: CameraSettings = CameraSettings()
    detector: DetectorSettings = DetectorSettings()
    retention: RetentionSettings = RetentionSettings()
    server: ServerSettings = ServerSettings()
