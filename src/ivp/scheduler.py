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

    def _matches_required_labels(self, device: Device, artifact: ArtifactSpec) -> bool:
        for key, value in artifact.scheduling.required_labels.items():
            if device.labels.get(key) != value:
                return False
        return True

    def _has_requested_capacity(self, device: Device, artifact: ArtifactSpec) -> bool:
        requests = artifact.scheduling.resource_requests
        if not requests:
            return True

        for resource, requested in requests.items():
            capacity = device.resource_capacity.get(resource, 0)

            if resource == "slots":
                available = capacity - device.queue_depth
            else:
                available = capacity

            if available < requested:
                return False

        return True

    def _affinity_miss_count(self, device: Device, artifact: ArtifactSpec) -> int:
        misses = 0
        for key, value in artifact.scheduling.preferred_labels.items():
            if device.labels.get(key) != value:
                misses += 1
        return misses

    def select_device(
        self,
        artifact: ArtifactSpec,
        excluded_device_ids: set[str] | None = None,
    ) -> Device:
        excluded_device_ids = excluded_device_ids or set()
        avoid_device_ids = set(artifact.scheduling.avoid_devices)
        preferred_device_ids = set(artifact.scheduling.preferred_devices)

        candidates = [
            d for d in self.inventory.healthy_devices_for(artifact.required_backends)
            if d.device_id not in excluded_device_ids
            and d.device_id not in avoid_device_ids
            and self._matches_required_labels(d, artifact)
            and self._has_requested_capacity(d, artifact)
        ]

        if not candidates:
            raise RuntimeError("no healthy device matches artifact backend requirements")

        return sorted(
            candidates,
            key=lambda d: (
                0 if d.device_id in preferred_device_ids else 1,
                self._affinity_miss_count(d, artifact),
                d.queue_depth,
                d.avg_latency_ms
                if d.avg_latency_ms is not None
                else BACKEND_PRIOR_LATENCY_MS.get(d.backend, float("inf")),
            ),
        )[0]
