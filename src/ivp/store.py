import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .models import Device, Heartbeat, PlatformEvent, ValidationResult


SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    device_id TEXT PRIMARY KEY,
    backend TEXT NOT NULL,
    status TEXT NOT NULL,
    queue_depth INTEGER NOT NULL,
    avg_latency_ms REAL,
    last_error TEXT,
    missed_heartbeats INTEGER NOT NULL,
    firmware_version TEXT,
    hardware_generation TEXT,
    labels_json TEXT NOT NULL DEFAULT '{}',
    resource_capacity_json TEXT NOT NULL DEFAULT '{}',
    updated_at_ms REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    source_repo TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    required_backends_json TEXT NOT NULL,
    latency_budget_ms REAL NOT NULL,
    correctness_required INTEGER NOT NULL,
    status TEXT NOT NULL,
    selected_device_id TEXT,
    result_json TEXT,
    created_at_ms REAL NOT NULL,
    updated_at_ms REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS heartbeats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    backend TEXT NOT NULL,
    healthy INTEGER NOT NULL,
    utilization REAL NOT NULL,
    last_latency_ms REAL,
    error TEXT,
    created_at_ms REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_ms REAL NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    job_id TEXT,
    artifact_id TEXT,
    device_id TEXT,
    details_json TEXT NOT NULL
);
"""


class SQLiteStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self.lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def upsert_device(
        self,
        device: Device,
        firmware_version: str | None = None,
        hardware_generation: str | None = None,
        labels: dict[str, str] | None = None,
        resource_capacity: dict[str, int] | None = None,
    ) -> None:
        now = time.time() * 1000
        labels = labels if labels is not None else device.labels
        resource_capacity = (
            resource_capacity
            if resource_capacity is not None
            else device.resource_capacity
        )
        firmware_version = firmware_version or device.firmware_version
        hardware_generation = hardware_generation or device.hardware_generation

        with self.lock:
            self.conn.execute(
                """
                INSERT INTO devices (
                    device_id, backend, status, queue_depth, avg_latency_ms,
                    last_error, missed_heartbeats, firmware_version,
                    hardware_generation, labels_json, resource_capacity_json,
                    updated_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    backend=excluded.backend,
                    status=excluded.status,
                    queue_depth=excluded.queue_depth,
                    avg_latency_ms=excluded.avg_latency_ms,
                    last_error=excluded.last_error,
                    missed_heartbeats=excluded.missed_heartbeats,
                    firmware_version=COALESCE(excluded.firmware_version, devices.firmware_version),
                    hardware_generation=COALESCE(excluded.hardware_generation, devices.hardware_generation),
                    labels_json=excluded.labels_json,
                    resource_capacity_json=excluded.resource_capacity_json,
                    updated_at_ms=excluded.updated_at_ms
                """,
                (
                    device.device_id,
                    device.backend,
                    device.status.value,
                    device.queue_depth,
                    device.avg_latency_ms,
                    device.last_error,
                    device.missed_heartbeats,
                    firmware_version,
                    hardware_generation,
                    json.dumps(labels or {}),
                    json.dumps(resource_capacity or {}),
                    now,
                ),
            )
            self.conn.commit()

    def record_heartbeat(self, heartbeat: Heartbeat) -> None:
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO heartbeats (
                    device_id, backend, healthy, utilization,
                    last_latency_ms, error, created_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    heartbeat.device_id,
                    heartbeat.backend,
                    int(heartbeat.healthy),
                    heartbeat.utilization,
                    heartbeat.last_latency_ms,
                    heartbeat.error,
                    time.time() * 1000,
                ),
            )
            self.conn.commit()

    def create_job(
        self,
        job_id: str,
        artifact_id: str,
        artifact_type: str,
        source_repo: str,
        artifact_path: str,
        required_backends: list[str],
        latency_budget_ms: float,
        correctness_required: bool,
    ) -> None:
        now = time.time() * 1000
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO jobs (
                    job_id, artifact_id, artifact_type, source_repo,
                    artifact_path, required_backends_json, latency_budget_ms,
                    correctness_required, status, created_at_ms, updated_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    artifact_id,
                    artifact_type,
                    source_repo,
                    artifact_path,
                    json.dumps(required_backends),
                    latency_budget_ms,
                    int(correctness_required),
                    "submitted",
                    now,
                    now,
                ),
            )
            self.conn.commit()

    def complete_job(self, job_id: str, result: ValidationResult) -> None:
        with self.lock:
            self.conn.execute(
                """
                UPDATE jobs
                SET status=?, selected_device_id=?, result_json=?, updated_at_ms=?
                WHERE job_id=?
                """,
                (
                    "passed" if result.passed_latency_budget and result.correctness_passed else "failed",
                    result.device_id,
                    result.model_dump_json(),
                    time.time() * 1000,
                    job_id,
                ),
            )
            self.conn.commit()

    def record_event(self, event: PlatformEvent) -> None:
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO events (
                    timestamp_ms, event_type, message,
                    job_id, artifact_id, device_id, details_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.timestamp_ms,
                    event.event_type,
                    event.message,
                    event.job_id,
                    event.artifact_id,
                    event.device_id,
                    json.dumps(event.details),
                ),
            )
            self.conn.commit()

    def get_job_report(self, job_id: str) -> dict[str, Any]:
        with self.lock:
            job = self.conn.execute(
                "SELECT * FROM jobs WHERE job_id=?",
                (job_id,),
            ).fetchone()

            if job is None:
                raise KeyError(job_id)

            events = self.conn.execute(
                "SELECT * FROM events WHERE job_id=? ORDER BY id ASC",
                (job_id,),
            ).fetchall()

            return {
                "job": dict(job),
                "events": [dict(row) for row in events],
            }

    def list_devices(self) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM devices ORDER BY device_id ASC"
            ).fetchall()
            return [dict(row) for row in rows]
