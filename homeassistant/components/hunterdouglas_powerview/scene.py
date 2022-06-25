"""Support for Powerview scenes from a Powerview hub."""
from __future__ import annotations

from typing import Any

from aiopvapi.resources.scene import Scene as PvScene

from homeassistant.components.scene import Scene
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, ROOM_NAME_UNICODE, STATE_ATTRIBUTE_ROOM_NAME
from .entity import HDEntity
from .model import PowerviewEntryData


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up powerview scene entries."""

    pv_entry: PowerviewEntryData = hass.data[DOMAIN][entry.entry_id]

    pvscenes = []
    for raw_scene in pv_entry.scene_data.values():
        scene = PvScene(raw_scene, pv_entry.api)
        room_name = pv_entry.room_data.get(scene.room_id, {}).get(ROOM_NAME_UNICODE, "")
        pvscenes.append(
            PowerViewScene(pv_entry.coordinator, pv_entry.device_info, room_name, scene)
        )
    async_add_entities(pvscenes)


class PowerViewScene(HDEntity, Scene):
    """Representation of a Powerview scene."""

    def __init__(self, coordinator, device_info, room_name, scene):
        """Initialize the scene."""
        super().__init__(coordinator, device_info, room_name, scene.id)
        self._scene = scene

    @property
    def name(self):
        """Return the name of the scene."""
        return self._scene.name

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {STATE_ATTRIBUTE_ROOM_NAME: self._room_name}

    @property
    def icon(self):
        """Icon to use in the frontend."""
        return "mdi:blinds"

    async def async_activate(self, **kwargs: Any) -> None:
        """Activate scene. Try to get entities into requested state."""
        await self._scene.activate()
