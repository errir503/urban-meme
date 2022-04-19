"""Support for control of Elk-M1 connected thermostats."""
from __future__ import annotations

from elkm1_lib.const import ThermostatFan, ThermostatMode, ThermostatSetting

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature
from homeassistant.components.climate.const import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    FAN_AUTO,
    FAN_ON,
    HVAC_MODE_COOL,
    HVAC_MODE_FAN_ONLY,
    HVAC_MODE_HEAT,
    HVAC_MODE_HEAT_COOL,
    HVAC_MODE_OFF,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PRECISION_WHOLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ElkEntity, create_elk_entities
from .const import DOMAIN

SUPPORT_HVAC = [
    HVAC_MODE_OFF,
    HVAC_MODE_HEAT,
    HVAC_MODE_COOL,
    HVAC_MODE_HEAT_COOL,
    HVAC_MODE_FAN_ONLY,
]
HASS_TO_ELK_HVAC_MODES = {
    HVAC_MODE_OFF: (ThermostatMode.OFF.value, ThermostatFan.AUTO.value),
    HVAC_MODE_HEAT: (ThermostatMode.HEAT.value, None),
    HVAC_MODE_COOL: (ThermostatMode.COOL.value, None),
    HVAC_MODE_HEAT_COOL: (ThermostatMode.AUTO.value, None),
    HVAC_MODE_FAN_ONLY: (ThermostatMode.OFF.value, ThermostatFan.ON.value),
}
ELK_TO_HASS_HVAC_MODES = {
    ThermostatMode.OFF.value: HVAC_MODE_OFF,
    ThermostatMode.COOL.value: HVAC_MODE_COOL,
    ThermostatMode.HEAT.value: HVAC_MODE_HEAT,
    ThermostatMode.EMERGENCY_HEAT.value: HVAC_MODE_HEAT,
    ThermostatMode.AUTO.value: HVAC_MODE_HEAT_COOL,
}
HASS_TO_ELK_FAN_MODES = {
    FAN_AUTO: (None, ThermostatFan.AUTO.value),
    FAN_ON: (None, ThermostatFan.ON.value),
}
ELK_TO_HASS_FAN_MODES = {
    ThermostatFan.AUTO.value: FAN_AUTO,
    ThermostatFan.ON.value: FAN_ON,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the Elk-M1 thermostat platform."""
    elk_data = hass.data[DOMAIN][config_entry.entry_id]
    entities: list[ElkEntity] = []
    elk = elk_data["elk"]
    create_elk_entities(
        elk_data, elk.thermostats, "thermostat", ElkThermostat, entities
    )
    async_add_entities(entities, True)


class ElkThermostat(ElkEntity, ClimateEntity):
    """Representation of an Elk-M1 Thermostat."""

    _attr_supported_features = (
        ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.AUX_HEAT
        | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    )

    def __init__(self, element, elk, elk_data):
        """Initialize climate entity."""
        super().__init__(element, elk, elk_data)
        self._state = None

    @property
    def temperature_unit(self):
        """Return the temperature unit."""
        return self._temperature_unit

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._element.current_temp

    @property
    def target_temperature(self):
        """Return the temperature we are trying to reach."""
        if self._element.mode in (
            ThermostatMode.HEAT.value,
            ThermostatMode.EMERGENCY_HEAT.value,
        ):
            return self._element.heat_setpoint
        if self._element.mode == ThermostatMode.COOL.value:
            return self._element.cool_setpoint
        return None

    @property
    def target_temperature_high(self):
        """Return the high target temperature."""
        return self._element.cool_setpoint

    @property
    def target_temperature_low(self):
        """Return the low target temperature."""
        return self._element.heat_setpoint

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return 1

    @property
    def current_humidity(self):
        """Return the current humidity."""
        return self._element.humidity

    @property
    def hvac_mode(self):
        """Return current operation ie. heat, cool, idle."""
        return self._state

    @property
    def hvac_modes(self):
        """Return the list of available operation modes."""
        return SUPPORT_HVAC

    @property
    def precision(self):
        """Return the precision of the system."""
        return PRECISION_WHOLE

    @property
    def is_aux_heat(self):
        """Return if aux heater is on."""
        return self._element.mode == ThermostatMode.EMERGENCY_HEAT.value

    @property
    def min_temp(self):
        """Return the minimum temperature supported."""
        return 1

    @property
    def max_temp(self):
        """Return the maximum temperature supported."""
        return 99

    @property
    def fan_mode(self):
        """Return the fan setting."""
        return ELK_TO_HASS_FAN_MODES.get(self._element.fan)

    def _elk_set(self, mode, fan):
        if mode is not None:
            self._element.set(ThermostatSetting.MODE.value, mode)
        if fan is not None:
            self._element.set(ThermostatSetting.FAN.value, fan)

    async def async_set_hvac_mode(self, hvac_mode):
        """Set thermostat operation mode."""
        thermostat_mode, fan_mode = HASS_TO_ELK_HVAC_MODES[hvac_mode]
        self._elk_set(thermostat_mode, fan_mode)

    async def async_turn_aux_heat_on(self):
        """Turn auxiliary heater on."""
        self._elk_set(ThermostatMode.EMERGENCY_HEAT.value, None)

    async def async_turn_aux_heat_off(self):
        """Turn auxiliary heater off."""
        self._elk_set(ThermostatMode.HEAT.value, None)

    @property
    def fan_modes(self):
        """Return the list of available fan modes."""
        return [FAN_AUTO, FAN_ON]

    async def async_set_fan_mode(self, fan_mode):
        """Set new target fan mode."""
        thermostat_mode, fan_mode = HASS_TO_ELK_HVAC_MODES[fan_mode]
        self._elk_set(thermostat_mode, fan_mode)

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        low_temp = kwargs.get(ATTR_TARGET_TEMP_LOW)
        high_temp = kwargs.get(ATTR_TARGET_TEMP_HIGH)
        if low_temp is not None:
            self._element.set(ThermostatSetting.HEAT_SETPOINT.value, round(low_temp))
        if high_temp is not None:
            self._element.set(ThermostatSetting.COOL_SETPOINT.value, round(high_temp))

    def _element_changed(self, element, changeset):
        self._state = ELK_TO_HASS_HVAC_MODES.get(self._element.mode)
        if self._state == HVAC_MODE_OFF and self._element.fan == ThermostatFan.ON.value:
            self._state = HVAC_MODE_FAN_ONLY
