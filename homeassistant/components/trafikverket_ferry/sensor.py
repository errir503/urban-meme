"""Ferry information for departures, provided by Trafikverket."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import TVDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

ATTR_FROM = "from_harbour"
ATTR_TO = "to_harbour"
ATTR_MODIFIED_TIME = "modified_time"
ATTR_OTHER_INFO = "other_info"

ICON = "mdi:ferry"
SCAN_INTERVAL = timedelta(minutes=5)


@dataclass
class TrafikverketRequiredKeysMixin:
    """Mixin for required keys."""

    value_fn: Callable[[dict[str, Any]], StateType]
    info_fn: Callable[[dict[str, Any]], StateType | list]


@dataclass
class TrafikverketSensorEntityDescription(
    SensorEntityDescription, TrafikverketRequiredKeysMixin
):
    """Describes Trafikverket sensor entity."""


SENSOR_TYPES: tuple[TrafikverketSensorEntityDescription, ...] = (
    TrafikverketSensorEntityDescription(
        key="departure_time",
        name="Departure Time",
        icon="mdi:clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data["departure_time"],
        info_fn=lambda data: data["departure_information"],
    ),
    TrafikverketSensorEntityDescription(
        key="departure_from",
        name="Departure From",
        icon="mdi:ferry",
        value_fn=lambda data: data["departure_from"],
        info_fn=lambda data: data["departure_information"],
    ),
    TrafikverketSensorEntityDescription(
        key="departure_to",
        name="Departure To",
        icon="mdi:ferry",
        value_fn=lambda data: data["departure_to"],
        info_fn=lambda data: data["departure_information"],
    ),
    TrafikverketSensorEntityDescription(
        key="departure_modified",
        name="Departure Modified",
        icon="mdi:clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data["departure_modified"],
        info_fn=lambda data: data["departure_information"],
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Trafikverket sensor entry."""

    coordinator: TVDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            FerrySensor(coordinator, entry.data[CONF_NAME], entry.entry_id, description)
            for description in SENSOR_TYPES
        ]
    )


class FerrySensor(CoordinatorEntity[TVDataUpdateCoordinator], SensorEntity):
    """Contains data about a ferry departure."""

    entity_description: TrafikverketSensorEntityDescription
    _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        coordinator: TVDataUpdateCoordinator,
        name: str,
        entry_id: str,
        entity_description: TrafikverketSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = f"{name} {entity_description.name}"
        self._attr_unique_id = f"{entry_id}-{entity_description.key}"
        self.entity_description = entity_description
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, entry_id)},
            manufacturer="Trafikverket",
            model="v1.2",
            name=name,
            configuration_url="https://api.trafikinfo.trafikverket.se/",
        )
        self._update_attr()

    def _update_attr(self) -> None:
        """Update _attr."""
        self._attr_native_value = self.entity_description.value_fn(
            self.coordinator.data
        )
        self._attr_extra_state_attributes = {
            "other_information": self.entity_description.info_fn(self.coordinator.data),
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attr()
        return super()._handle_coordinator_update()
