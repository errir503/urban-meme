"""Entity for the SleepIQ integration."""
from abc import abstractmethod

from asyncsleepiq import SleepIQBed, SleepIQSleeper

from homeassistant.core import callback
from homeassistant.helpers import device_registry
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import ICON_OCCUPIED, SENSOR_TYPES


def device_from_bed(bed: SleepIQBed) -> DeviceInfo:
    """Create a device given a bed."""
    return DeviceInfo(
        connections={(device_registry.CONNECTION_NETWORK_MAC, bed.mac_addr)},
        manufacturer="SleepNumber",
        name=bed.name,
        model=bed.model,
    )


class SleepIQEntity(Entity):
    """Implementation of a SleepIQ entity."""

    def __init__(self, bed: SleepIQBed) -> None:
        """Initialize the SleepIQ entity."""
        self.bed = bed
        self._attr_device_info = device_from_bed(bed)


class SleepIQSensor(CoordinatorEntity):
    """Implementation of a SleepIQ sensor."""

    _attr_icon = ICON_OCCUPIED

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        bed: SleepIQBed,
        sleeper: SleepIQSleeper,
        name: str,
    ) -> None:
        """Initialize the SleepIQ sensor entity."""
        super().__init__(coordinator)
        self.sleeper = sleeper
        self.bed = bed
        self._attr_device_info = device_from_bed(bed)

        self._attr_name = f"SleepNumber {bed.name} {sleeper.name} {SENSOR_TYPES[name]}"
        self._attr_unique_id = f"{bed.id}_{sleeper.name}_{name}"
        self._async_update_attrs()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._async_update_attrs()
        super()._handle_coordinator_update()

    @callback
    @abstractmethod
    def _async_update_attrs(self) -> None:
        """Update sensor attributes."""


class SleepIQBedCoordinator(CoordinatorEntity):
    """Implementation of a SleepIQ sensor."""

    _attr_icon = ICON_OCCUPIED

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        bed: SleepIQBed,
    ) -> None:
        """Initialize the SleepIQ sensor entity."""
        super().__init__(coordinator)
        self.bed = bed
        self._attr_device_info = device_from_bed(bed)
