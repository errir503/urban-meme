"""Support for Rain Bird Irrigation system LNK WiFi Module."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RainbirdUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


RAIN_DELAY_ENTITY_DESCRIPTION = SensorEntityDescription(
    key="raindelay",
    name="Raindelay",
    icon="mdi:water-off",
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entry for a Rain Bird sensor."""
    async_add_entities(
        [
            RainBirdSensor(
                hass.data[DOMAIN][config_entry.entry_id],
                RAIN_DELAY_ENTITY_DESCRIPTION,
            )
        ]
    )


class RainBirdSensor(CoordinatorEntity[RainbirdUpdateCoordinator], SensorEntity):
    """A sensor implementation for Rain Bird device."""

    def __init__(
        self,
        coordinator: RainbirdUpdateCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the Rain Bird sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.serial_number}-{description.key}"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> StateType:
        """Return the value reported by the sensor."""
        return self.coordinator.data.rain_delay
