"""Support for deCONZ locks."""

from __future__ import annotations

from typing import Any

from pydeconz.models.event import EventType
from pydeconz.models.light.lock import Lock
from pydeconz.models.sensor.door_lock import DoorLock

from homeassistant.components.lock import DOMAIN, LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
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
    def async_add_lock_from_light(_: EventType, lock_id: str) -> None:
        """Add lock from deCONZ."""
        lock = gateway.api.lights.locks[lock_id]
        async_add_entities([DeconzLock(lock, gateway)])

    config_entry.async_on_unload(
        gateway.api.lights.locks.subscribe(
            gateway.evaluate_add_device(async_add_lock_from_light),
            EventType.ADDED,
        )
    )
    for lock_id in gateway.api.lights.locks:
        async_add_lock_from_light(EventType.ADDED, lock_id)

    @callback
    def async_add_lock_from_sensor(_: EventType, lock_id: str) -> None:
        """Add lock from deCONZ."""
        lock = gateway.api.sensors.door_lock[lock_id]
        async_add_entities([DeconzLock(lock, gateway)])

    config_entry.async_on_unload(
        gateway.api.sensors.door_lock.subscribe(
            gateway.evaluate_add_device(async_add_lock_from_sensor),
            EventType.ADDED,
        )
    )
    for lock_id in gateway.api.sensors.door_lock:
        async_add_lock_from_sensor(EventType.ADDED, lock_id)


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
