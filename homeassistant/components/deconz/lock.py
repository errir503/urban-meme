"""Support for deCONZ locks."""

from __future__ import annotations

from typing import Any

from pydeconz.models.light.lock import Lock
from pydeconz.models.sensor.door_lock import DoorLock

from homeassistant.components.lock import DOMAIN, LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .deconz_device import DeconzDevice
from .gateway import get_gateway_from_config_entry


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up locks for deCONZ component."""
    gateway = get_gateway_from_config_entry(hass, config_entry)
    gateway.entities[DOMAIN] = set()

    @callback
    def async_add_lock_from_light(lights: list[Lock] | None = None) -> None:
        """Add lock from deCONZ."""
        entities = []

        if lights is None:
            lights = list(gateway.api.lights.locks.values())

        for light in lights:

            if (
                isinstance(light, Lock)
                and light.unique_id not in gateway.entities[DOMAIN]
            ):
                entities.append(DeconzLock(light, gateway))

        if entities:
            async_add_entities(entities)

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            gateway.signal_new_light,
            async_add_lock_from_light,
        )
    )

    @callback
    def async_add_lock_from_sensor(sensors: list[DoorLock] | None = None) -> None:
        """Add lock from deCONZ."""
        entities = []

        if sensors is None:
            sensors = list(gateway.api.sensors.door_lock.values())

        for sensor in sensors:

            if (
                isinstance(sensor, DoorLock)
                and sensor.unique_id not in gateway.entities[DOMAIN]
            ):
                entities.append(DeconzLock(sensor, gateway))

        if entities:
            async_add_entities(entities)

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            gateway.signal_new_sensor,
            async_add_lock_from_sensor,
        )
    )

    async_add_lock_from_light()
    async_add_lock_from_sensor()


class DeconzLock(DeconzDevice, LockEntity):
    """Representation of a deCONZ lock."""

    TYPE = DOMAIN
    _device: DoorLock | Lock

    @property
    def is_locked(self) -> bool:
        """Return true if lock is on."""
        return self._device.is_locked

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the lock."""
        await self._device.lock()

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the lock."""
        await self._device.unlock()
