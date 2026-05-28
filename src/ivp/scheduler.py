from .inventory import DeviceInventory
from .models import ArtifactSpec, Device


BACKEND_PRIOR_LATENCY_MS = {
    "cuda": 1.5,
    "mock_gpu": 2.0,
    "metal": 2.5,
    "cpu": 4.0,
}


class Scheduler:
    def __init__(self, inventory: DeviceInventory) -> None:
        self.inventory = inventory

    def select_device(
        self,
        artifact: ArtifactSpec,
        excluded_device_ids: set[str] | None = None,
    ) -> Device:
        excluded_device_ids = excluded_device_ids or set()

        candidates = [
            d for d in self.inventory.healthy_devices_for(artifact.required_backends)
            if d.device_id not in excluded_device_ids
        ]

        if not candidates:
            raise RuntimeError("no healthy device matches artifact backend requirements")

        return sorted(
            candidates,
            key=lambda d: (
                d.queue_depth,
                d.avg_latency_ms
                if d.avg_latency_ms is not None
                else BACKEND_PRIOR_LATENCY_MS.get(d.backend, float("inf")),
            ),
        )[0]