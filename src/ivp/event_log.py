import time
from typing import Any

from .models import PlatformEvent


class EventLog:
    def __init__(self) -> None:
        self.events: list[PlatformEvent] = []

    def record(
        self,
        event_type: str,
        message: str,
        job_id: str | None = None,
        artifact_id: str | None = None,
        device_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.events.append(
            PlatformEvent(
                timestamp_ms=round(time.time() * 1000, 3),
                event_type=event_type,
                message=message,
                job_id=job_id,
                artifact_id=artifact_id,
                device_id=device_id,
                details=details or {},
            )
        )

    def snapshot(self) -> list[PlatformEvent]:
        return list(self.events)