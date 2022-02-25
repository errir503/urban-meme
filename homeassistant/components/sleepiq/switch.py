"""Support for SleepIQ switches."""
from __future__ import annotations

from typing import Any

from asyncsleepiq import SleepIQBed

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SleepIQData, SleepIQPauseUpdateCoordinator
from .entity import SleepIQBedCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sleep number switches."""
    data: SleepIQData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SleepNumberPrivateSwitch(data.pause_coordinator, bed)
        for bed in data.client.beds.values()
    )


class SleepNumberPrivateSwitch(SleepIQBedCoordinator, SwitchEntity):
    """Representation of SleepIQ privacy mode."""

    def __init__(
        self, coordinator: SleepIQPauseUpdateCoordinator, bed: SleepIQBed
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, bed)
        self._attr_name = f"SleepNumber {bed.name} Pause Mode"
        self._attr_unique_id = f"{bed.id}-pause-mode"

    @property
    def is_on(self) -> bool:
        """Return whether the switch is on or off."""
        return bool(self.bed.paused)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on switch."""
        await self.bed.set_pause_mode(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off switch."""
        await self.bed.set_pause_mode(False)
