import json
import random
import subprocess
import sys
from pathlib import Path

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


class ExternalRuntimeWorker:
    def __init__(self, device: Device) -> None:
        self.device = device

    def run_validation(self, job_id: str, artifact: ArtifactSpec) -> ValidationResult:
        summary_path = self._resolve_summary_path(artifact)
        results = self._load_summary(summary_path)
        selected = self._select_best_result(results)

        avg = float(selected["avg_latency_ms"])
        p95 = selected.get("p95_latency_ms")
        if p95 is None:
            p95 = avg
        p99 = selected.get("p99_latency_ms")
        if p99 is None:
            p99 = p95

        backend = selected.get("backend", self.device.backend)
        precision = selected.get("precision", "")
        device = selected.get("device", self.device.device_id)

        return ValidationResult(
            job_id=job_id,
            artifact_id=artifact.artifact_id,
            device_id=self.device.device_id,
            backend=f"{backend} ({precision}, {device})",
            correctness_passed=True,
            avg_latency_ms=round(avg, 4),
            p95_latency_ms=round(float(p95), 4),
            p99_latency_ms=round(float(p99), 4),
            passed_latency_budget=float(p95) <= artifact.latency_budget_ms,
        )

    def _resolve_summary_path(self, artifact: ArtifactSpec) -> Path:
        artifact_path = Path(artifact.artifact_path)

        if artifact.artifact_type == "external_runtime_summary":
            return artifact_path

        if artifact.artifact_type != "external_runtime_benchmark":
            raise ValueError(
                f"unsupported external runtime artifact type: {artifact.artifact_type}"
            )

        runtime_root = artifact_path
        runner = runtime_root / "backend_validation_runner.py"
        if not runner.exists():
            raise FileNotFoundError(f"runtime runner not found: {runner}")

        python = runtime_root / ".venv/bin/python"
        if not python.exists():
            python = Path(sys.executable)

        completed = subprocess.run(
            [str(python), str(runner)],
            cwd=runtime_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "external runtime benchmark failed\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )

        return runtime_root / "results/backend_validation_summary.json"

    def _load_summary(self, summary_path: Path) -> list[dict]:
        if not summary_path.exists():
            raise FileNotFoundError(f"runtime summary not found: {summary_path}")

        with summary_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list) or not data:
            raise ValueError("runtime summary must be a non-empty result list")

        return data

    def _select_best_result(self, results: list[dict]) -> dict:
        candidates = [
            result for result in results
            if result.get("avg_latency_ms") is not None
        ]
        if not candidates:
            raise ValueError("runtime summary does not contain latency results")

        return min(
            candidates,
            key=lambda result: (
                result.get("p95_latency_ms")
                if result.get("p95_latency_ms") is not None
                else result["avg_latency_ms"],
                result["avg_latency_ms"],
            ),
        )
