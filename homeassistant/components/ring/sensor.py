"""Component providing HA sensor support for Ring Door Bell/Chimes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN
from .entity import RingEntityMixin


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a sensor for a Ring device."""
    devices = hass.data[DOMAIN][config_entry.entry_id]["devices"]

    entities = [
        description.cls(config_entry.entry_id, device, description)
        for device_type in ("chimes", "doorbots", "authorized_doorbots", "stickup_cams")
        for description in SENSOR_TYPES
        if device_type in description.category
        for device in devices[device_type]
        if not (device_type == "battery" and device.battery_life is None)
    ]

    async_add_entities(entities)


class RingSensor(RingEntityMixin, SensorEntity):
    """A sensor implementation for Ring device."""

    entity_description: RingSensorEntityDescription

    def __init__(
        self,
        config_entry_id,
        device,
        description: RingSensorEntityDescription,
    ) -> None:
        """Initialize a sensor for Ring device."""
        super().__init__(config_entry_id, device)
        self.entity_description = description
        self._attr_unique_id = f"{device.id}-{description.key}"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        sensor_type = self.entity_description.key
        if sensor_type == "volume":
            return self._device.volume

        if sensor_type == "battery":
            return self._device.battery_life


class HealthDataRingSensor(RingSensor):
    """Ring sensor that relies on health data."""

    # These sensors are data hungry and not useful. Disable by default.
    _attr_entity_registry_enabled_default = False

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        await super().async_added_to_hass()

        await self.ring_objects["health_data"].async_track_device(
            self._device, self._health_update_callback
        )

    async def async_will_remove_from_hass(self) -> None:
        """Disconnect callbacks."""
        await super().async_will_remove_from_hass()

        self.ring_objects["health_data"].async_untrack_device(
            self._device, self._health_update_callback
        )

    @callback
    def _health_update_callback(self, _health_data):
        """Call update method."""
        self.async_write_ha_state()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        sensor_type = self.entity_description.key
        if sensor_type == "wifi_signal_category":
            return self._device.wifi_signal_category

        if sensor_type == "wifi_signal_strength":
            return self._device.wifi_signal_strength


class HistoryRingSensor(RingSensor):
    """Ring sensor that relies on history data."""

    _latest_event: dict[str, Any] | None = None

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        await super().async_added_to_hass()

        await self.ring_objects["history_data"].async_track_device(
            self._device, self._history_update_callback
        )

    async def async_will_remove_from_hass(self) -> None:
        """Disconnect callbacks."""
        await super().async_will_remove_from_hass()

        self.ring_objects["history_data"].async_untrack_device(
            self._device, self._history_update_callback
        )

    @callback
    def _history_update_callback(self, history_data):
        """Call update method."""
        if not history_data:
            return

        kind = self.entity_description.kind
        found = None
        if kind is None:
            found = history_data[0]
        else:
            for entry in history_data:
                if entry["kind"] == kind:
                    found = entry
                    break

        if not found:
            return

        self._latest_event = found
        self.async_write_ha_state()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self._latest_event is None:
            return None

        return self._latest_event["created_at"]

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = super().extra_state_attributes

        if self._latest_event:
            attrs["created_at"] = self._latest_event["created_at"]
            attrs["answered"] = self._latest_event["answered"]
            attrs["recording_status"] = self._latest_event["recording"]["status"]
            attrs["category"] = self._latest_event["kind"]

        return attrs


@dataclass
class RingRequiredKeysMixin:
    """Mixin for required keys."""

    category: list[str]
    cls: type[RingSensor]


@dataclass
class RingSensorEntityDescription(SensorEntityDescription, RingRequiredKeysMixin):
    """Describes Ring sensor entity."""

    kind: str | None = None


SENSOR_TYPES: tuple[RingSensorEntityDescription, ...] = (
    RingSensorEntityDescription(
        key="battery",
        category=["doorbots", "authorized_doorbots", "stickup_cams"],
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        cls=RingSensor,
    ),
    RingSensorEntityDescription(
        key="last_activity",
        translation_key="last_activity",
        category=["doorbots", "authorized_doorbots", "stickup_cams"],
        icon="mdi:history",
        device_class=SensorDeviceClass.TIMESTAMP,
        cls=HistoryRingSensor,
    ),
    RingSensorEntityDescription(
        key="last_ding",
        translation_key="last_ding",
        category=["doorbots", "authorized_doorbots"],
        icon="mdi:history",
        kind="ding",
        device_class=SensorDeviceClass.TIMESTAMP,
        cls=HistoryRingSensor,
    ),
    RingSensorEntityDescription(
        key="last_motion",
        translation_key="last_motion",
        category=["doorbots", "authorized_doorbots", "stickup_cams"],
        icon="mdi:history",
        kind="motion",
        device_class=SensorDeviceClass.TIMESTAMP,
        cls=HistoryRingSensor,
    ),
    RingSensorEntityDescription(
        key="volume",
        translation_key="volume",
        category=["chimes", "doorbots", "authorized_doorbots", "stickup_cams"],
        icon="mdi:bell-ring",
        cls=RingSensor,
    ),
    RingSensorEntityDescription(
        key="wifi_signal_category",
        translation_key="wifi_signal_category",
        category=["chimes", "doorbots", "authorized_doorbots", "stickup_cams"],
        icon="mdi:wifi",
        cls=HealthDataRingSensor,
    ),
    RingSensorEntityDescription(
        key="wifi_signal_strength",
        translation_key="wifi_signal_strength",
        category=["chimes", "doorbots", "authorized_doorbots", "stickup_cams"],
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        icon="mdi:wifi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        cls=HealthDataRingSensor,
    ),
)
