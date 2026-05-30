from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DeviceStatus(str, Enum):
    HEALTHY = "healthy"
    BUSY = "busy"
    QUARANTINED = "quarantined"
    OFFLINE = "offline"


class SchedulingConstraints(BaseModel):
    required_labels: dict[str, str] = Field(default_factory=dict)
    preferred_labels: dict[str, str] = Field(default_factory=dict)
    resource_requests: dict[str, int] = Field(default_factory=dict)
    preferred_devices: list[str] = Field(default_factory=list)
    avoid_devices: list[str] = Field(default_factory=list)
    allow_preemption: bool = False
    priority: int = 0


class ArtifactSpec(BaseModel):
    artifact_id: str
    artifact_type: str
    source_repo: str
    artifact_path: str
    required_backends: list[str]
    latency_budget_ms: float
    correctness_required: bool = True
    scheduling: SchedulingConstraints = Field(default_factory=SchedulingConstraints)


class Device(BaseModel):
    device_id: str
    backend: str
    status: DeviceStatus = DeviceStatus.HEALTHY
    queue_depth: int = 0
    avg_latency_ms: float | None = None
    last_error: str | None = None
    missed_heartbeats: int = 0
    firmware_version: str | None = None
    hardware_generation: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    resource_capacity: dict[str, int] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    job_id: str
    artifact_id: str
    device_id: str
    backend: str
    correctness_passed: bool
    avg_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    passed_latency_budget: bool
    retry_count: int = 0


class Heartbeat(BaseModel):
    device_id: str
    backend: str
    healthy: bool
    utilization: float
    last_latency_ms: float | None = None
    error: str | None = None


class PlatformEvent(BaseModel):
    timestamp_ms: float
    event_type: str
    message: str
    job_id: str | None = None
    artifact_id: str | None = None
    device_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
