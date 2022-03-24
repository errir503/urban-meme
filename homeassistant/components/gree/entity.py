"""Entity object for shared properties of Gree entities."""
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .bridge import DeviceDataUpdateCoordinator
from .const import DOMAIN


class GreeEntity(CoordinatorEntity[DeviceDataUpdateCoordinator]):
    """Generic Gree entity (base class)."""

    def __init__(self, coordinator: DeviceDataUpdateCoordinator, desc: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._desc = desc
        self._name = f"{coordinator.device.device_info.name}"
        self._mac = coordinator.device.device_info.mac

    @property
    def name(self):
        """Return the name of the node."""
        return f"{self._name} {self._desc}"

    @property
    def unique_id(self):
        """Return the unique id based for the node."""
        return f"{self._mac}_{self._desc}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return info about the device."""
        return DeviceInfo(
            connections={(CONNECTION_NETWORK_MAC, self._mac)},
            identifiers={(DOMAIN, self._mac)},
            manufacturer="Gree",
            name=self._name,
        )
