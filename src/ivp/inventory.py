from .models import Device, DeviceStatus, Heartbeat


class DeviceInventory:
    def __init__(self) -> None:
        self.devices: dict[str, Device] = {}

    def register(self, device: Device) -> None:
        self.devices[device.device_id] = device

    def healthy_devices_for(self, backends: list[str]) -> list[Device]:
        return [
            d for d in self.devices.values()
            if d.backend in backends and d.status == DeviceStatus.HEALTHY
        ]

    def quarantine(self, device_id: str, reason: str) -> None:
        device = self.devices[device_id]
        device.status = DeviceStatus.QUARANTINED
        device.last_error = reason

    def mark_busy(self, device_id: str) -> None:
        self.devices[device_id].status = DeviceStatus.BUSY

    def mark_healthy(self, device_id: str, latency_ms: float) -> None:
        device = self.devices[device_id]
        device.status = DeviceStatus.HEALTHY
        device.avg_latency_ms = latency_ms
        device.queue_depth = max(0, device.queue_depth - 1)
        device.last_error = None
    def apply_heartbeat(self, heartbeat: Heartbeat) -> None:
        if heartbeat.device_id not in self.devices:
            self.register(
                Device(
                    device_id=heartbeat.device_id,
                    backend=heartbeat.backend,
                )
            )

        device = self.devices[heartbeat.device_id]
        device.backend = heartbeat.backend
        device.missed_heartbeats = 0

        if heartbeat.healthy:
            device.status = DeviceStatus.HEALTHY
            device.last_error = None
            if heartbeat.last_latency_ms is not None:
                device.avg_latency_ms = heartbeat.last_latency_ms
        else:
            device.status = DeviceStatus.QUARANTINED
            device.last_error = heartbeat.error or "worker reported unhealthy"

    def mark_heartbeat_missed(self, device_id: str) -> None:
        device = self.devices[device_id]
        device.missed_heartbeats += 1

        if device.missed_heartbeats >= 3:
            device.status = DeviceStatus.OFFLINE
            device.last_error = "missed heartbeat threshold exceeded"

    def snapshot(self) -> list[Device]:
        return list(self.devices.values())