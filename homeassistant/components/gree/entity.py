"""Entity object for shared properties of Gree entities."""
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .bridge import DeviceDataUpdateCoordinator
from .const import DOMAIN


class GreeEntity(CoordinatorEntity[DeviceDataUpdateCoordinator]):
    """Generic Gree entity (base class)."""

    def __init__(self, coordinator: DeviceDataUpdateCoordinator, desc: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._desc = desc
        name = coordinator.device.device_info.name
        mac = coordinator.device.device_info.mac
        self._attr_name = f"{name} {desc}"
        self._attr_unique_id = f"{mac}_{desc}"
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_NETWORK_MAC, mac)},
            identifiers={(DOMAIN, mac)},
            manufacturer="Gree",
            name=name,
        )
