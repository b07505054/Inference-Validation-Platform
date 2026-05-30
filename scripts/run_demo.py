import json
import argparse
import sys

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ivp.event_log import EventLog
from src.ivp.inventory import DeviceInventory
from src.ivp.report import write_markdown_report, write_report
from src.ivp.scheduler import Scheduler
from src.ivp.validation import ValidationPipeline
from src.ivp.heartbeat import HeartbeatMonitor
from src.ivp.models import ArtifactSpec, Device, Heartbeat


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact",
        default="configs/sample_artifact.json",
        help="artifact config path relative to project root",
    )
    parser.add_argument(
        "--prefer-cpu-first",
        action="store_true",
        help="seed CPU latency lower than mock_gpu to demonstrate retry/quarantine",
    )
    args = parser.parse_args()
    artifact = ArtifactSpec.model_validate_json(
        (ROOT / args.artifact).read_text(encoding="utf-8")
    )
    
    inventory = DeviceInventory()
    event_log = EventLog()
    event_log.record(
        event_type="job.submitted",
        message="submitted compiler-produced artifact for validation",
        job_id="job-001",
        artifact_id=artifact.artifact_id,
        details={
            "artifact_type": artifact.artifact_type,
            "required_backends": artifact.required_backends,
            "latency_budget_ms": artifact.latency_budget_ms,
        },
    )
    inventory.register(Device(device_id="cpu-worker-1", backend="cpu"))
    inventory.register(Device(device_id="mock-asic-worker-1", backend="mock_gpu"))
    heartbeat_monitor = HeartbeatMonitor(inventory)

    heartbeat_monitor.receive(
        Heartbeat(
            device_id="cpu-worker-1",
            backend="cpu",
            healthy=True,
            utilization=0.15,
            last_latency_ms=1.0 if args.prefer_cpu_first else 4.8,
        )
    )
    event_log.record(
        event_type="heartbeat.received",
        message="cpu worker reported healthy heartbeat",
        device_id="cpu-worker-1",
        details={
            "backend": "cpu",
            "utilization": 0.15,
            "last_latency_ms": 1.0 if args.prefer_cpu_first else 4.8,
        },
    )

    heartbeat_monitor.receive(
        Heartbeat(
            device_id="mock-asic-worker-1",
            backend="mock_gpu",
            healthy=True,
            utilization=0.35,
            last_latency_ms=2.2,
        )
    )
    event_log.record(
        event_type="heartbeat.received",
        message="mock accelerator worker reported healthy heartbeat",
        device_id="mock-asic-worker-1",
        details={
            "backend": "mock_gpu",
            "utilization": 0.35,
            "last_latency_ms": 2.2,
        },
    )
    scheduler = Scheduler(inventory)
    pipeline = ValidationPipeline(
        inventory=inventory,
        scheduler=scheduler,
        max_retries=1,
        event_log=event_log,
    )
    inventory.register(Device(device_id="stale-cuda-worker-1", backend="cuda"))

    heartbeat_monitor.miss("stale-cuda-worker-1")
    heartbeat_monitor.miss("stale-cuda-worker-1")
    heartbeat_monitor.miss("stale-cuda-worker-1")
    event_log.record(
        event_type="heartbeat.missed_threshold",
        message="stale cuda worker marked offline after 3 missed heartbeats",
        device_id="stale-cuda-worker-1",
        details={
            "missed_heartbeats": 3,
            "status": "offline",
        },
    )
    result = pipeline.run("job-001", artifact)

    markdown_report_path = ROOT / "reports/job-001.md"
    write_markdown_report(
        markdown_report_path,
        artifact,
        result,
        devices=inventory.snapshot(),
        events=event_log.snapshot(),
    )

    print(json.dumps(result.model_dump(), indent=2))
    print(f"wrote markdown report: {markdown_report_path}")

    print("\nDevice inventory:")
    for device in inventory.devices.values():
        print(json.dumps(device.model_dump(), indent=2))
    print("\nEvent timeline:")
    for event in event_log.snapshot():
        print(json.dumps(event.model_dump(), indent=2))

if __name__ == "__main__":
    main()
