import json
from pathlib import Path

from .models import ArtifactSpec, Device, PlatformEvent, ValidationResult


def write_report(
    path: Path,
    artifact: ArtifactSpec,
    result: ValidationResult,
    devices: list[Device] | None = None,
    events: list[PlatformEvent] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "artifact": artifact.model_dump(),
        "validation_result": result.model_dump(),
        "fleet_snapshot": [
            device.model_dump()
            for device in devices or []
        ],
        "event_timeline": [
            event.model_dump()
            for event in events or []
        ],
    }

    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_markdown_report(
    path: Path,
    artifact: ArtifactSpec,
    result: ValidationResult,
    devices: list[Device] | None = None,
    events: list[PlatformEvent] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    status = "PASS" if (
        result.correctness_passed and result.passed_latency_budget
    ) else "FAIL"

    lines = [
        f"# Inference Validation Report: {result.job_id}",
        "",
        f"**Result:** {status}",
        f"**Artifact:** `{artifact.artifact_id}`",
        f"**Artifact type:** `{artifact.artifact_type}`",
        f"**Source repo:** `{artifact.source_repo}`",
        f"**Latency budget:** p95 <= {artifact.latency_budget_ms:.4f} ms",
        "",
        "## Final Validation Result",
        "",
        "| Field | Value |",
        "|---|---:|",
        f"| Device | `{result.device_id}` |",
        f"| Backend | `{result.backend}` |",
        f"| Correctness | `{result.correctness_passed}` |",
        f"| Avg latency | {result.avg_latency_ms:.4f} ms |",
        f"| p95 latency | {result.p95_latency_ms:.4f} ms |",
        f"| p99 latency | {result.p99_latency_ms:.4f} ms |",
        f"| Passed latency budget | `{result.passed_latency_budget}` |",
        f"| Retry count | {result.retry_count} |",
        "",
        "## Fleet Snapshot",
        "",
        "| Device | Backend | Status | Avg latency | Last error | Missed heartbeats |",
        "|---|---|---|---:|---|---:|",
    ]

    for device in devices or []:
        avg_latency = (
            f"{device.avg_latency_ms:.4f} ms"
            if device.avg_latency_ms is not None
            else "n/a"
        )
        last_error = device.last_error or ""
        lines.append(
            f"| `{device.device_id}` | `{device.backend}` | "
            f"`{device.status.value}` | {avg_latency} | {last_error} | "
            f"{device.missed_heartbeats} |"
        )

    lines.extend([
        "",
        "## Event Timeline",
        "",
        "| Event | Device | Message |",
        "|---|---|---|",
    ])

    for event in events or []:
        device_id = f"`{event.device_id}`" if event.device_id else ""
        lines.append(
            f"| `{event.event_type}` | {device_id} | {event.message} |"
        )

    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")