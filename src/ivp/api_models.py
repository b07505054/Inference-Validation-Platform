from pydantic import BaseModel, Field

from .models import ArtifactSpec


class RegisterWorkerRequest(BaseModel):
    device_id: str
    backend: str
    firmware_version: str | None = None
    hardware_generation: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    resource_capacity: dict[str, int] = Field(default_factory=dict)


class SubmitJobRequest(BaseModel):
    job_id: str
    artifact: ArtifactSpec
    max_retries: int = 1
    prefer_cpu_first: bool = False
