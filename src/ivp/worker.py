import random
from .models import ArtifactSpec, Device, ValidationResult


class MockWorker:
    def __init__(self, device: Device) -> None:
        self.device = device

    def run_validation(self, job_id: str, artifact: ArtifactSpec) -> ValidationResult:
        base_latency = 2.0 if self.device.backend == "mock_gpu" else 4.0
        jitter = random.uniform(0.0, 1.5)
        avg = base_latency + jitter
        p95 = avg * 1.25
        p99 = avg * 1.45

        return ValidationResult(
            job_id=job_id,
            artifact_id=artifact.artifact_id,
            device_id=self.device.device_id,
            backend=self.device.backend,
            correctness_passed=True,
            avg_latency_ms=round(avg, 4),
            p95_latency_ms=round(p95, 4),
            p99_latency_ms=round(p99, 4),
            passed_latency_budget=p95 <= artifact.latency_budget_ms,
        )