"""Support for SwitchBot binary sensors."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SwitchbotDataUpdateCoordinator
from .entity import SwitchbotEntity

PARALLEL_UPDATES = 1

BINARY_SENSOR_TYPES: dict[str, BinarySensorEntityDescription] = {
    "calibration": BinarySensorEntityDescription(
        key="calibration",
        name="Calibration",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "motion_detected": BinarySensorEntityDescription(
        key="pir_state",
        name="Motion detected",
        device_class=BinarySensorDeviceClass.MOTION,
    ),
    "contact_open": BinarySensorEntityDescription(
        key="contact_open",
        name="Door open",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    "contact_timeout": BinarySensorEntityDescription(
        key="contact_timeout",
        name="Door timeout",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "is_light": BinarySensorEntityDescription(
        key="is_light",
        name="Light",
        device_class=BinarySensorDeviceClass.LIGHT,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Switchbot curtain based on a config entry."""
    coordinator: SwitchbotDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    unique_id = entry.unique_id
    assert unique_id is not None
    async_add_entities(
        [
            SwitchBotBinarySensor(
                coordinator,
                unique_id,
                binary_sensor,
                entry.data[CONF_ADDRESS],
                entry.data[CONF_NAME],
            )
            for binary_sensor in coordinator.data["data"]
            if binary_sensor in BINARY_SENSOR_TYPES
        ]
    )


class SwitchBotBinarySensor(SwitchbotEntity, BinarySensorEntity):
    """Representation of a Switchbot binary sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SwitchbotDataUpdateCoordinator,
        unique_id: str,
        binary_sensor: str,
        mac: str,
        switchbot_name: str,
    ) -> None:
        """Initialize the Switchbot sensor."""
        super().__init__(coordinator, unique_id, mac, name=switchbot_name)
        self._sensor = binary_sensor
        self._attr_unique_id = f"{unique_id}-{binary_sensor}"
        self.entity_description = BINARY_SENSOR_TYPES[binary_sensor]
        self._attr_name = self.entity_description.name

    @property
    def is_on(self) -> bool:
        """Return the state of the sensor."""
        return self.data["data"][self._sensor]
