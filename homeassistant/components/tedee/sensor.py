"""Tedee sensor entities."""
from collections.abc import Callable
from dataclasses import dataclass

from pytedee_async import TedeeLock

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import TedeeDescriptionEntity


@dataclass(frozen=True, kw_only=True)
class TedeeSensorEntityDescription(SensorEntityDescription):
    """Describes Tedee sensor entity."""

    value_fn: Callable[[TedeeLock], float | None]


ENTITIES: tuple[TedeeSensorEntityDescription, ...] = (
    TedeeSensorEntityDescription(
        key="battery_sensor",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda lock: lock.battery_level,
    ),
    TedeeSensorEntityDescription(
        key="pullspring_duration",
        translation_key="pullspring_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:timer-lock-open",
        value_fn=lambda lock: lock.duration_pullspring,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tedee sensor entity."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    for entity_description in ENTITIES:
        async_add_entities(
            [
                TedeeSensorEntity(lock, coordinator, entity_description)
                for lock in coordinator.data.values()
            ]
        )

    def _async_add_new_lock(lock_id: int) -> None:
        lock = coordinator.data[lock_id]
        async_add_entities(
            [
                TedeeSensorEntity(lock, coordinator, entity_description)
                for entity_description in ENTITIES
            ]
        )

    coordinator.new_lock_callbacks.append(_async_add_new_lock)


class TedeeSensorEntity(TedeeDescriptionEntity, SensorEntity):
    """Tedee sensor entity."""

    entity_description: TedeeSensorEntityDescription

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self._lock)
