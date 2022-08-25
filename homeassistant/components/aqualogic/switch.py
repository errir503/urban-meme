"""Support for AquaLogic switches."""
from __future__ import annotations

from typing import Any

from aqualogic.core import States
import voluptuous as vol

from homeassistant.components.switch import PLATFORM_SCHEMA, SwitchEntity
from homeassistant.const import CONF_MONITORED_CONDITIONS
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import DOMAIN, UPDATE_TOPIC

SWITCH_TYPES = {
    "lights": "Lights",
    "filter": "Filter",
    "filter_low_speed": "Filter Low Speed",
    "aux_1": "Aux 1",
    "aux_2": "Aux 2",
    "aux_3": "Aux 3",
    "aux_4": "Aux 4",
    "aux_5": "Aux 5",
    "aux_6": "Aux 6",
    "aux_7": "Aux 7",
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_MONITORED_CONDITIONS, default=list(SWITCH_TYPES)): vol.All(
            cv.ensure_list, [vol.In(SWITCH_TYPES)]
        )
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the switch platform."""
    switches = []

    processor = hass.data[DOMAIN]
    for switch_type in config[CONF_MONITORED_CONDITIONS]:
        switches.append(AquaLogicSwitch(processor, switch_type))

    async_add_entities(switches)


class AquaLogicSwitch(SwitchEntity):
    """Switch implementation for the AquaLogic component."""

    _attr_should_poll = False

    def __init__(self, processor, switch_type):
        """Initialize switch."""
        self._processor = processor
        self._state_name = {
            "lights": States.LIGHTS,
            "filter": States.FILTER,
            "filter_low_speed": States.FILTER_LOW_SPEED,
            "aux_1": States.AUX_1,
            "aux_2": States.AUX_2,
            "aux_3": States.AUX_3,
            "aux_4": States.AUX_4,
            "aux_5": States.AUX_5,
            "aux_6": States.AUX_6,
            "aux_7": States.AUX_7,
        }[switch_type]
        self._attr_name = f"AquaLogic {SWITCH_TYPES[switch_type]}"

    @property
    def is_on(self):
        """Return true if device is on."""
        if (panel := self._processor.panel) is None:
            return False
        state = panel.get_state(self._state_name)
        return state

    def turn_on(self, **kwargs: Any) -> None:
        """Turn the device on."""
        if (panel := self._processor.panel) is None:
            return
        panel.set_state(self._state_name, True)

    def turn_off(self, **kwargs: Any) -> None:
        """Turn the device off."""
        if (panel := self._processor.panel) is None:
            return
        panel.set_state(self._state_name, False)

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self.async_on_remove(
            async_dispatcher_connect(self.hass, UPDATE_TOPIC, self.async_write_ha_state)
        )
