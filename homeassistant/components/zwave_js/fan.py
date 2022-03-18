"""Support for Z-Wave fans."""
from __future__ import annotations

import math
from typing import Any, cast

from zwave_js_server.client import Client as ZwaveClient
from zwave_js_server.const import TARGET_VALUE_PROPERTY, CommandClass
from zwave_js_server.const.command_class.thermostat import (
    THERMOSTAT_FAN_OFF_PROPERTY,
    THERMOSTAT_FAN_STATE_PROPERTY,
)
from zwave_js_server.model.value import Value as ZwaveValue

from homeassistant.components.fan import (
    DOMAIN as FAN_DOMAIN,
    SUPPORT_PRESET_MODE,
    SUPPORT_SET_SPEED,
    FanEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.percentage import (
    int_states_in_range,
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)

from .const import DATA_CLIENT, DOMAIN
from .discovery import ZwaveDiscoveryInfo
from .discovery_data_template import FanSpeedDataTemplate
from .entity import ZWaveBaseEntity
from .helpers import get_value_of_zwave_value

SUPPORTED_FEATURES = SUPPORT_SET_SPEED

DEFAULT_SPEED_RANGE = (1, 99)  # off is not included

ATTR_FAN_STATE = "fan_state"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Z-Wave Fan from Config Entry."""
    client: ZwaveClient = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]

    @callback
    def async_add_fan(info: ZwaveDiscoveryInfo) -> None:
        """Add Z-Wave fan."""
        entities: list[ZWaveBaseEntity] = []
        if info.platform_hint == "configured_fan_speed":
            entities.append(ConfiguredSpeedRangeZwaveFan(config_entry, client, info))
        elif info.platform_hint == "thermostat_fan":
            entities.append(ZwaveThermostatFan(config_entry, client, info))
        else:
            entities.append(ZwaveFan(config_entry, client, info))

        async_add_entities(entities)

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            f"{DOMAIN}_{config_entry.entry_id}_add_{FAN_DOMAIN}",
            async_add_fan,
        )
    )


class ZwaveFan(ZWaveBaseEntity, FanEntity):
    """Representation of a Z-Wave fan."""

    def __init__(
        self, config_entry: ConfigEntry, client: ZwaveClient, info: ZwaveDiscoveryInfo
    ) -> None:
        """Initialize the fan."""
        super().__init__(config_entry, client, info)
        self._target_value = self.get_zwave_value(TARGET_VALUE_PROPERTY)

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed percentage of the fan."""
        if percentage == 0:
            zwave_speed = 0
        else:
            zwave_speed = math.ceil(
                percentage_to_ranged_value(DEFAULT_SPEED_RANGE, percentage)
            )

        await self.info.node.async_set_value(self._target_value, zwave_speed)

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn the device on."""
        if percentage is None:
            # Value 255 tells device to return to previous value
            await self.info.node.async_set_value(self._target_value, 255)
        else:
            await self.async_set_percentage(percentage)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the device off."""
        await self.info.node.async_set_value(self._target_value, 0)

    @property
    def is_on(self) -> bool | None:
        """Return true if device is on (speed above 0)."""
        if self.info.primary_value.value is None:
            # guard missing value
            return None
        return bool(self.info.primary_value.value > 0)

    @property
    def percentage(self) -> int | None:
        """Return the current speed percentage."""
        if self.info.primary_value.value is None:
            # guard missing value
            return None
        return ranged_value_to_percentage(
            DEFAULT_SPEED_RANGE, self.info.primary_value.value
        )

    @property
    def percentage_step(self) -> float:
        """Return the step size for percentage."""
        return 1

    @property
    def speed_count(self) -> int:
        """Return the number of speeds the fan supports."""
        return int_states_in_range(DEFAULT_SPEED_RANGE)

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return SUPPORTED_FEATURES


class ConfiguredSpeedRangeZwaveFan(ZwaveFan):
    """A Zwave fan with a configured speed range (e.g., 1-24 is low)."""

    def __init__(
        self, config_entry: ConfigEntry, client: ZwaveClient, info: ZwaveDiscoveryInfo
    ) -> None:
        """Initialize the fan."""
        super().__init__(config_entry, client, info)
        self.data_template = cast(
            FanSpeedDataTemplate, self.info.platform_data_template
        )

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed percentage of the fan."""
        zwave_speed = self.percentage_to_zwave_speed(percentage)
        await self.info.node.async_set_value(self._target_value, zwave_speed)

    @property
    def available(self) -> bool:
        """Return whether the entity is available."""
        return super().available and self.has_speed_configuration

    @property
    def percentage(self) -> int | None:
        """Return the current speed percentage."""
        if self.info.primary_value.value is None:
            # guard missing value
            return None

        return self.zwave_speed_to_percentage(self.info.primary_value.value)

    @property
    def percentage_step(self) -> float:
        """Return the step size for percentage."""
        # This is the same implementation as the base fan type, but
        # it needs to be overridden here because the ZwaveFan does
        # something different for fans with unknown speeds.
        return 100 / self.speed_count

    @property
    def has_speed_configuration(self) -> bool:
        """Check if the speed configuration is valid."""
        return self.data_template.get_speed_config(self.info.platform_data) is not None

    @property
    def speed_configuration(self) -> list[int]:
        """Return the speed configuration for this fan."""
        speed_configuration = self.data_template.get_speed_config(
            self.info.platform_data
        )

        # Entity should be unavailable if this isn't set
        assert speed_configuration is not None

        return speed_configuration

    @property
    def speed_count(self) -> int:
        """Return the number of speeds the fan supports."""
        return len(self.speed_configuration)

    def percentage_to_zwave_speed(self, percentage: int) -> int:
        """Map a percentage to a ZWave speed."""
        if percentage == 0:
            return 0

        # Since the percentage steps are computed with rounding, we have to
        # search to find the appropriate speed.
        for speed_limit in self.speed_configuration:
            step_percentage = self.zwave_speed_to_percentage(speed_limit)
            if percentage <= step_percentage:
                return speed_limit

        # This shouldn't actually happen; the last entry in
        # `self.speed_configuration` should map to 100%.
        return self.speed_configuration[-1]

    def zwave_speed_to_percentage(self, zwave_speed: int) -> int:
        """Convert a Zwave speed to a percentage."""
        if zwave_speed == 0:
            return 0

        percentage = 0.0
        for speed_limit in self.speed_configuration:
            percentage += self.percentage_step
            if zwave_speed <= speed_limit:
                break

        # This choice of rounding function is to provide consistency with how
        # the UI handles steps e.g., for a 3-speed fan, you get steps at 33,
        # 67, and 100.
        return round(percentage)


class ZwaveThermostatFan(ZWaveBaseEntity, FanEntity):
    """Representation of a Z-Wave thermostat fan."""

    _fan_mode: ZwaveValue
    _fan_off: ZwaveValue | None = None
    _fan_state: ZwaveValue | None = None

    def __init__(
        self, config_entry: ConfigEntry, client: ZwaveClient, info: ZwaveDiscoveryInfo
    ) -> None:
        """Initialize the thermostat fan."""
        super().__init__(config_entry, client, info)

        self._fan_mode = self.info.primary_value

        self._fan_off = self.get_zwave_value(
            THERMOSTAT_FAN_OFF_PROPERTY,
            CommandClass.THERMOSTAT_FAN_MODE,
            add_to_watched_value_ids=True,
        )
        self._fan_state = self.get_zwave_value(
            THERMOSTAT_FAN_STATE_PROPERTY,
            CommandClass.THERMOSTAT_FAN_STATE,
            add_to_watched_value_ids=True,
        )

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn the device on."""
        if not self._fan_off:
            raise HomeAssistantError("Unhandled action turn_on")
        await self.info.node.async_set_value(self._fan_off, False)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the device off."""
        if not self._fan_off:
            raise HomeAssistantError("Unhandled action turn_off")
        await self.info.node.async_set_value(self._fan_off, True)

    @property
    def is_on(self) -> bool | None:
        """Return true if device is on."""
        if (value := get_value_of_zwave_value(self._fan_off)) is None:
            return None
        return not cast(bool, value)

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode, e.g., auto, smart, interval, favorite."""
        value = get_value_of_zwave_value(self._fan_mode)
        if value is None or str(value) not in self._fan_mode.metadata.states:
            return None
        return cast(str, self._fan_mode.metadata.states[str(value)])

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""

        try:
            new_state = next(
                int(state)
                for state, label in self._fan_mode.metadata.states.items()
                if label == preset_mode
            )
        except StopIteration:
            raise ValueError(f"Received an invalid fan mode: {preset_mode}") from None

        await self.info.node.async_set_value(self._fan_mode, new_state)

    @property
    def preset_modes(self) -> list[str] | None:
        """Return a list of available preset modes."""
        if not self._fan_mode.metadata.states:
            return None
        return list(self._fan_mode.metadata.states.values())

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return SUPPORT_PRESET_MODE

    @property
    def fan_state(self) -> str | None:
        """Return the current state, Idle, Running, etc."""
        value = get_value_of_zwave_value(self._fan_state)
        if (
            value is None
            or self._fan_state is None
            or str(value) not in self._fan_state.metadata.states
        ):
            return None
        return cast(str, self._fan_state.metadata.states[str(value)])

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Return the optional state attributes."""
        attrs = {}

        if state := self.fan_state:
            attrs[ATTR_FAN_STATE] = state

        return attrs
