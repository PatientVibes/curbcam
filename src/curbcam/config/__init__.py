"""Pydantic-typed configuration model + YAML persistence."""

from curbcam.config.schema import (
    CameraSettings,
    DetectorSettings,
    RetentionSettings,
    ServerSettings,
    Settings,
)
from curbcam.config.store import ConfigStore
from curbcam.detector.types import CropRect

__all__ = [
    "CameraSettings",
    "ConfigStore",
    "CropRect",
    "DetectorSettings",
    "RetentionSettings",
    "ServerSettings",
    "Settings",
]
