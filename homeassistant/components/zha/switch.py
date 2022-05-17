"""Switches on Zigbee Home Automation networks."""
from __future__ import annotations

import functools
from typing import Any

from zigpy.zcl.clusters.general import OnOff
from zigpy.zcl.foundation import Status

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, Platform
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .core import discovery
from .core.const import (
    CHANNEL_ON_OFF,
    DATA_ZHA,
    SIGNAL_ADD_ENTITIES,
    SIGNAL_ATTR_UPDATED,
)
from .core.registries import ZHA_ENTITIES
from .entity import ZhaEntity, ZhaGroupEntity

STRICT_MATCH = functools.partial(ZHA_ENTITIES.strict_match, Platform.SWITCH)
GROUP_MATCH = functools.partial(ZHA_ENTITIES.group_match, Platform.SWITCH)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Zigbee Home Automation switch from config entry."""
    entities_to_create = hass.data[DATA_ZHA][Platform.SWITCH]

    unsub = async_dispatcher_connect(
        hass,
        SIGNAL_ADD_ENTITIES,
        functools.partial(
            discovery.async_add_entities, async_add_entities, entities_to_create
        ),
    )
    config_entry.async_on_unload(unsub)


@STRICT_MATCH(channel_names=CHANNEL_ON_OFF)
class Switch(ZhaEntity, SwitchEntity):
    """ZHA switch."""

    def __init__(self, unique_id, zha_device, channels, **kwargs):
        """Initialize the ZHA switch."""
        super().__init__(unique_id, zha_device, channels, **kwargs)
        self._on_off_channel = self.cluster_channels.get(CHANNEL_ON_OFF)

    @property
    def is_on(self) -> bool:
        """Return if the switch is on based on the statemachine."""
        if self._on_off_channel.on_off is None:
            return False
        return self._on_off_channel.on_off

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the entity on."""
        result = await self._on_off_channel.turn_on()
        if not result:
            return
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the entity off."""
        result = await self._on_off_channel.turn_off()
        if not result:
            return
        self.async_write_ha_state()

    @callback
    def async_set_state(self, attr_id: int, attr_name: str, value: Any):
        """Handle state update from channel."""
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Run when about to be added to hass."""
        await super().async_added_to_hass()
        self.async_accept_signal(
            self._on_off_channel, SIGNAL_ATTR_UPDATED, self.async_set_state
        )

    async def async_update(self) -> None:
        """Attempt to retrieve on off state from the switch."""
        await super().async_update()
        if self._on_off_channel:
            await self._on_off_channel.get_attribute_value("on_off", from_cache=False)


@GROUP_MATCH()
class SwitchGroup(ZhaGroupEntity, SwitchEntity):
    """Representation of a switch group."""

    def __init__(
        self, entity_ids: list[str], unique_id: str, group_id: int, zha_device, **kwargs
    ) -> None:
        """Initialize a switch group."""
        super().__init__(entity_ids, unique_id, group_id, zha_device, **kwargs)
        self._available: bool
        self._state: bool
        group = self.zha_device.gateway.get_group(self._group_id)
        self._on_off_channel = group.endpoint[OnOff.cluster_id]

    @property
    def is_on(self) -> bool:
        """Return if the switch is on based on the statemachine."""
        return bool(self._state)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the entity on."""
        result = await self._on_off_channel.on()
        if isinstance(result, Exception) or result[1] is not Status.SUCCESS:
            return
        self._state = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the entity off."""
        result = await self._on_off_channel.off()
        if isinstance(result, Exception) or result[1] is not Status.SUCCESS:
            return
        self._state = False
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Query all members and determine the light group state."""
        all_states = [self.hass.states.get(x) for x in self._entity_ids]
        states: list[State] = list(filter(None, all_states))
        on_states = [state for state in states if state.state == STATE_ON]

        self._state = len(on_states) > 0
        self._available = any(state.state != STATE_UNAVAILABLE for state in states)
