"""Support for LiteJet scenes."""
from typing import Any

from pylitejet import LiteJet

from homeassistant.components.scene import Scene
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

ATTR_NUMBER = "number"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entry."""

    system: LiteJet = hass.data[DOMAIN]

    entities = []
    for i in system.scenes():
        name = await system.get_scene_name(i)
        entities.append(LiteJetScene(config_entry.entry_id, system, i, name))

    async_add_entities(entities, True)


class LiteJetScene(Scene):
    """Representation of a single LiteJet scene."""

    def __init__(self, entry_id, lj: LiteJet, i, name):  # pylint: disable=invalid-name
        """Initialize the scene."""
        self._entry_id = entry_id
        self._lj = lj
        self._index = i
        self._name = name

    @property
    def name(self):
        """Return the name of the scene."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique identifier for this scene."""
        return f"{self._entry_id}_{self._index}"

    @property
    def extra_state_attributes(self):
        """Return the device-specific state attributes."""
        return {ATTR_NUMBER: self._index}

    async def async_activate(self, **kwargs: Any) -> None:
        """Activate the scene."""
        await self._lj.activate_scene(self._index)

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Scenes are only enabled by explicit user choice."""
        return False
