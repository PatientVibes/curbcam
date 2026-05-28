"""Runner + event-bus that wires camera → detector → storage."""
from curbcam.pipeline.events import EventBus, EventEnvelope

__all__ = ["EventBus", "EventEnvelope"]
