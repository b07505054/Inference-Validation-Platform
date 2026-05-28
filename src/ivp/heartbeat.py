from .inventory import DeviceInventory
from .models import Heartbeat


class HeartbeatMonitor:
    def __init__(self, inventory: DeviceInventory) -> None:
        self.inventory = inventory

    def receive(self, heartbeat: Heartbeat) -> None:
        self.inventory.apply_heartbeat(heartbeat)

    def miss(self, device_id: str) -> None:
        self.inventory.mark_heartbeat_missed(device_id)