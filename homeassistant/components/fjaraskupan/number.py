"""Support for sensors."""
from __future__ import annotations

from fjaraskupan import Device

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import TIME_MINUTES
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, Entity, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import Coordinator, async_setup_entry_platform


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities dynamically through discovery."""

    def _constructor(coordinator: Coordinator) -> list[Entity]:
        return [
            PeriodicVentingTime(
                coordinator, coordinator.device, coordinator.device_info
            ),
        ]

    async_setup_entry_platform(hass, config_entry, async_add_entities, _constructor)


class PeriodicVentingTime(CoordinatorEntity[Coordinator], NumberEntity):
    """Periodic Venting."""

    _attr_max_value: float = 59
    _attr_min_value: float = 0
    _attr_step: float = 1
    _attr_entity_category = EntityCategory.CONFIG
    _attr_unit_of_measurement = TIME_MINUTES

    def __init__(
        self,
        coordinator: Coordinator,
        device: Device,
        device_info: DeviceInfo,
    ) -> None:
        """Init number entities."""
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"{device.address}-periodic-venting"
        self._attr_device_info = device_info
        self._attr_name = f"{device_info['name']} Periodic Venting"

    @property
    def value(self) -> float | None:
        """Return the entity value to represent the entity state."""
        if data := self.coordinator.data:
            return data.periodic_venting
        return None

    async def async_set_value(self, value: float) -> None:
        """Set new value."""
        await self._device.send_periodic_venting(int(value))
        self.coordinator.async_set_updated_data(self._device.state)
