from .event_log import EventLog
from .inventory import DeviceInventory
from .models import ArtifactSpec, ValidationResult
from .scheduler import Scheduler
from .worker import MockWorker


class ValidationPipeline:
    def __init__(
        self,
        inventory: DeviceInventory,
        scheduler: Scheduler,
        max_retries: int = 1,
        event_log: EventLog | None = None,
    ) -> None:
        self.inventory = inventory
        self.scheduler = scheduler
        self.max_retries = max_retries
        self.event_log = event_log

    def run(self, job_id: str, artifact: ArtifactSpec) -> ValidationResult:
        excluded: set[str] = set()
        last_result: ValidationResult | None = None

        for attempt in range(self.max_retries + 1):
            device = self.scheduler.select_device(
                artifact,
                excluded_device_ids=excluded,
            )

            if self.event_log:
                self.event_log.record(
                    event_type="scheduler.selected_device",
                    message=f"selected {device.device_id} for validation attempt {attempt}",
                    job_id=job_id,
                    artifact_id=artifact.artifact_id,
                    device_id=device.device_id,
                    details={
                        "backend": device.backend,
                        "queue_depth": device.queue_depth,
                        "avg_latency_ms": device.avg_latency_ms,
                        "attempt": attempt,
                    },
                )

            self.inventory.mark_busy(device.device_id)

            result = MockWorker(device).run_validation(
                job_id=job_id,
                artifact=artifact,
            )
            result.retry_count = attempt

            if result.correctness_passed and result.passed_latency_budget:
                self.inventory.mark_healthy(
                    device.device_id,
                    result.avg_latency_ms,
                )

                if self.event_log:
                    self.event_log.record(
                        event_type="validation.passed",
                        message="validation passed correctness and latency budget",
                        job_id=job_id,
                        artifact_id=artifact.artifact_id,
                        device_id=device.device_id,
                        details=result.model_dump(),
                    )

                return result

            reason = (
                "latency budget failed"
                if not result.passed_latency_budget
                else "correctness failed"
            )

            self.inventory.quarantine(device.device_id, reason)
            excluded.add(device.device_id)
            last_result = result

            if self.event_log:
                self.event_log.record(
                    event_type="validation.failed",
                    message=reason,
                    job_id=job_id,
                    artifact_id=artifact.artifact_id,
                    device_id=device.device_id,
                    details=result.model_dump(),
                )
                self.event_log.record(
                    event_type="device.quarantined",
                    message=f"{device.device_id} quarantined: {reason}",
                    job_id=job_id,
                    artifact_id=artifact.artifact_id,
                    device_id=device.device_id,
                )

        if last_result is None:
            raise RuntimeError("validation did not run")

        return last_result