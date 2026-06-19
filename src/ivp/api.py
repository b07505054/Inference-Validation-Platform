from pathlib import Path

from fastapi import FastAPI, HTTPException, Response

from .api_models import RegisterWorkerRequest, SubmitJobRequest
from .event_log import EventLog
from .heartbeat import HeartbeatMonitor
from .inventory import DeviceInventory
from .models import Device, Heartbeat
from .metrics import render_prometheus_metrics
from .report import write_markdown_report, write_report
from .scheduler import Scheduler
from .store import SQLiteStore
from .validation import ValidationPipeline


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"

app = FastAPI(title="Inference Validation Platform")

inventory = DeviceInventory()
store = SQLiteStore(DATA_DIR / "ivp.sqlite3")
heartbeat_monitor = HeartbeatMonitor(inventory)


@app.post("/workers/register")
def register_worker(request: RegisterWorkerRequest) -> dict:
    device = Device(
        device_id=request.device_id,
        backend=request.backend,
        firmware_version=request.firmware_version,
        hardware_generation=request.hardware_generation,
        labels=request.labels,
        resource_capacity=request.resource_capacity,
    )

    inventory.register(device)
    store.upsert_device(
        device,
        firmware_version=request.firmware_version,
        hardware_generation=request.hardware_generation,
        labels=request.labels,
        resource_capacity=request.resource_capacity,
    )

    return {
        "status": "registered",
        "device": device.model_dump(),
    }


@app.post("/workers/heartbeat")
def heartbeat(heartbeat: Heartbeat) -> dict:
    heartbeat_monitor.receive(heartbeat)
    store.record_heartbeat(heartbeat)

    device = inventory.devices[heartbeat.device_id]
    store.upsert_device(device)

    return {
        "status": "heartbeat_recorded",
        "device": device.model_dump(),
    }


@app.post("/jobs/submit")
def submit_job(request: SubmitJobRequest) -> dict:
    artifact = request.artifact

    if request.prefer_cpu_first and "cpu-worker-1" in inventory.devices:
        inventory.devices["cpu-worker-1"].avg_latency_ms = 1.0

    store.create_job(
        job_id=request.job_id,
        artifact_id=artifact.artifact_id,
        artifact_type=artifact.artifact_type,
        source_repo=artifact.source_repo,
        artifact_path=artifact.artifact_path,
        required_backends=artifact.required_backends,
        latency_budget_ms=artifact.latency_budget_ms,
        correctness_required=artifact.correctness_required,
    )

    event_log = EventLog(store=store)
    event_log.record(
        event_type="job.submitted",
        message="submitted compiler-produced artifact for validation",
        job_id=request.job_id,
        artifact_id=artifact.artifact_id,
        details={
            "artifact_type": artifact.artifact_type,
            "required_backends": artifact.required_backends,
            "latency_budget_ms": artifact.latency_budget_ms,
        },
    )

    scheduler = Scheduler(inventory)
    pipeline = ValidationPipeline(
        inventory=inventory,
        scheduler=scheduler,
        max_retries=request.max_retries,
        event_log=event_log,
    )

    try:
        result = pipeline.run(request.job_id, artifact)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    store.complete_job(request.job_id, result)
    for device in inventory.snapshot():
        store.upsert_device(device)

    json_report_path = REPORT_DIR / f"{request.job_id}.json"
    markdown_report_path = REPORT_DIR / f"{request.job_id}.md"

    write_report(
        json_report_path,
        artifact,
        result,
        devices=inventory.snapshot(),
        events=event_log.snapshot(),
    )
    write_markdown_report(
        markdown_report_path,
        artifact,
        result,
        devices=inventory.snapshot(),
        events=event_log.snapshot(),
    )

    return {
        "status": "completed",
        "result": result.model_dump(),
        "json_report": str(json_report_path),
        "markdown_report": str(markdown_report_path),
    }


@app.get("/reports/{job_id}")
def get_report(job_id: str) -> dict:
    try:
        return store.get_job_report(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc


@app.get("/devices")
def list_devices() -> dict:
    return {
        "devices": store.list_devices(),
    }


@app.get("/metrics")
def prometheus_metrics():
    return Response(
        content=render_prometheus_metrics(store.control_plane_metrics()),
        media_type="text/plain; version=0.0.4",
    )
