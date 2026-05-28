"""Frame-source abstraction. Detector never depends on this directly."""

from curbcam.camera.base import Camera
from curbcam.camera.file_replay import FileReplaySource

__all__ = ["Camera", "FileReplaySource"]
