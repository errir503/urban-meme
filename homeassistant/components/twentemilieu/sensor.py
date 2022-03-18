"""Support for Twente Milieu sensors."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from twentemilieu import WasteType

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN


@dataclass
class TwenteMilieuSensorDescriptionMixin:
    """Define an entity description mixin."""

    waste_type: WasteType


@dataclass
class TwenteMilieuSensorDescription(
    SensorEntityDescription, TwenteMilieuSensorDescriptionMixin
):
    """Describe an Ambient PWS binary sensor."""


SENSORS: tuple[TwenteMilieuSensorDescription, ...] = (
    TwenteMilieuSensorDescription(
        key="tree",
        waste_type=WasteType.TREE,
        name="Christmas Tree Pickup",
        icon="mdi:pine-tree",
        device_class=SensorDeviceClass.DATE,
    ),
    TwenteMilieuSensorDescription(
        key="Non-recyclable",
        waste_type=WasteType.NON_RECYCLABLE,
        name="Non-recyclable Waste Pickup",
        icon="mdi:delete-empty",
        device_class=SensorDeviceClass.DATE,
    ),
    TwenteMilieuSensorDescription(
        key="Organic",
        waste_type=WasteType.ORGANIC,
        name="Organic Waste Pickup",
        icon="mdi:delete-empty",
        device_class=SensorDeviceClass.DATE,
    ),
    TwenteMilieuSensorDescription(
        key="Paper",
        waste_type=WasteType.PAPER,
        name="Paper Waste Pickup",
        icon="mdi:delete-empty",
        device_class=SensorDeviceClass.DATE,
    ),
    TwenteMilieuSensorDescription(
        key="Plastic",
        waste_type=WasteType.PACKAGES,
        name="Packages Waste Pickup",
        icon="mdi:delete-empty",
        device_class=SensorDeviceClass.DATE,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Twente Milieu sensor based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.data[CONF_ID]]
    async_add_entities(
        TwenteMilieuSensor(coordinator, description, entry) for description in SENSORS
    )


class TwenteMilieuSensor(CoordinatorEntity[dict[WasteType, list[date]]], SensorEntity):
    """Defines a Twente Milieu sensor."""

    entity_description: TwenteMilieuSensorDescription

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        description: TwenteMilieuSensorDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the Twente Milieu entity."""
        super().__init__(coordinator=coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{entry.data[CONF_ID]}_{description.key}"
        self._attr_device_info = DeviceInfo(
            configuration_url="https://www.twentemilieu.nl",
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, str(entry.data[CONF_ID]))},
            manufacturer="Twente Milieu",
            name="Twente Milieu",
        )

    @property
    def native_value(self) -> date | None:
        """Return the state of the sensor."""
        if not (dates := self.coordinator.data[self.entity_description.waste_type]):
            return None
        return dates[0]
