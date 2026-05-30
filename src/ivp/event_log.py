import time
from typing import Any

from .models import PlatformEvent


class EventLog:
    def __init__(self, store=None) -> None:
        self.events: list[PlatformEvent] = []
        self.store = store

    def record(
        self,
        event_type: str,
        message: str,
        job_id: str | None = None,
        artifact_id: str | None = None,
        device_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        event = PlatformEvent(
            timestamp_ms=round(time.time() * 1000, 3),
            event_type=event_type,
            message=message,
            job_id=job_id,
            artifact_id=artifact_id,
            device_id=device_id,
            details=details or {},
        )
        self.events.append(event)

        if self.store is not None:
            self.store.record_event(event)

    def snapshot(self) -> list[PlatformEvent]:
        return list(self.events)