"""curbcam web layer: FastAPI app + Supervisor."""

from curbcam.web.app import create_app
from curbcam.web.supervisor import Supervisor

__all__ = ["Supervisor", "create_app"]
