import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ivp.event_log import EventLog
from src.ivp.inventory import DeviceInventory
from src.ivp.models import ArtifactSpec, Device, Heartbeat
from src.ivp.heartbeat import HeartbeatMonitor
from src.ivp.report import write_markdown_report, write_report
from src.ivp.scheduler import Scheduler
from src.ivp.validation import ValidationPipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate heterogeneous-inference-runtime benchmark output."
    )
    parser.add_argument(
        "--artifact",
        default="configs/external_runtime_summary_artifact.json",
        help="artifact config path relative to project root",
    )
    parser.add_argument(
        "--job-id",
        default="external-runtime-job-001",
    )
    parser.add_argument(
        "--output-prefix",
        default="reports/external-runtime-job-001",
    )
    args = parser.parse_args()

    artifact = ArtifactSpec.model_validate_json(
        (ROOT / args.artifact).read_text(encoding="utf-8")
    )

    inventory = DeviceInventory()
    event_log = EventLog()
    device = Device(
        device_id="heterogeneous-runtime-worker-1",
        backend="external_runtime",
        firmware_version="local-python-runner",
        hardware_generation="local-macos-workstation",
        labels={
            "runtime": "heterogeneous-inference-runtime",
            "mode": (
                "live_benchmark"
                if artifact.artifact_type == "external_runtime_benchmark"
                else "artifact_ingestion"
            ),
        },
        resource_capacity={"slots": 1},
    )
    inventory.register(device)

    heartbeat_monitor = HeartbeatMonitor(inventory)
    heartbeat_monitor.receive(
        Heartbeat(
            device_id=device.device_id,
            backend=device.backend,
            healthy=True,
            utilization=0.25,
            last_latency_ms=2.5,
        )
    )

    event_log.record(
        event_type="job.submitted",
        message="submitted external runtime artifact for validation",
        job_id=args.job_id,
        artifact_id=artifact.artifact_id,
        details=artifact.model_dump(),
    )
    event_log.record(
        event_type="heartbeat.received",
        message="external runtime worker reported healthy heartbeat",
        device_id=device.device_id,
        details=device.model_dump(),
    )

    pipeline = ValidationPipeline(
        inventory=inventory,
        scheduler=Scheduler(inventory),
        max_retries=0,
        event_log=event_log,
    )
    result = pipeline.run(args.job_id, artifact)

    output_prefix = ROOT / args.output_prefix
    write_report(
        output_prefix.with_suffix(".json"),
        artifact,
        result,
        devices=inventory.snapshot(),
        events=event_log.snapshot(),
    )
    write_markdown_report(
        output_prefix.with_suffix(".md"),
        artifact,
        result,
        devices=inventory.snapshot(),
        events=event_log.snapshot(),
    )

    print(json.dumps(result.model_dump(), indent=2))
    print(f"wrote json report: {output_prefix.with_suffix('.json')}")
    print(f"wrote markdown report: {output_prefix.with_suffix('.md')}")


if __name__ == "__main__":
    main()
