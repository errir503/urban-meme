"""Demo platform that has two fake binary sensors."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import DOMAIN


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Demo binary sensor platform."""
    async_add_entities(
        [
            DemoBinarySensor(
                "binary_1",
                "Basement Floor Wet",
                False,
                BinarySensorDeviceClass.MOISTURE,
            ),
            DemoBinarySensor(
                "binary_2", "Movement Backyard", True, BinarySensorDeviceClass.MOTION
            ),
        ]
    )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Demo config entry."""
    await async_setup_platform(hass, {}, async_add_entities)


class DemoBinarySensor(BinarySensorEntity):
    """representation of a Demo binary sensor."""

    _attr_should_poll = False

    def __init__(
        self,
        unique_id: str,
        name: str,
        state: bool,
        device_class: BinarySensorDeviceClass,
    ) -> None:
        """Initialize the demo sensor."""
        self._unique_id = unique_id
        self._attr_name = name
        self._state = state
        self._attr_device_class = device_class

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={
                # Serial numbers are unique identifiers within a specific domain
                (DOMAIN, self.unique_id)
            },
            name=self.name,
        )

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return self._unique_id

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self._state
