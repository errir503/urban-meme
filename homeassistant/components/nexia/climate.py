"""Support for Nexia / Trane XL thermostats."""
from __future__ import annotations

from nexia.const import (
    HOLD_PERMANENT,
    HOLD_RESUME_SCHEDULE,
    OPERATION_MODE_AUTO,
    OPERATION_MODE_COOL,
    OPERATION_MODE_HEAT,
    OPERATION_MODE_OFF,
    SYSTEM_STATUS_COOL,
    SYSTEM_STATUS_HEAT,
    SYSTEM_STATUS_IDLE,
)
from nexia.home import NexiaHome
from nexia.thermostat import NexiaThermostat
from nexia.util import find_humidity_setpoint
from nexia.zone import NexiaThermostatZone
import voluptuous as vol

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_HUMIDITY,
    ATTR_HVAC_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, TEMP_CELSIUS, TEMP_FAHRENHEIT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_AIRCLEANER_MODE,
    ATTR_DEHUMIDIFY_SETPOINT,
    ATTR_DEHUMIDIFY_SUPPORTED,
    ATTR_HUMIDIFY_SETPOINT,
    ATTR_HUMIDIFY_SUPPORTED,
    ATTR_RUN_MODE,
    ATTR_ZONE_STATUS,
    DOMAIN,
)
from .coordinator import NexiaDataUpdateCoordinator
from .entity import NexiaThermostatZoneEntity
from .util import percent_conv

PARALLEL_UPDATES = 1  # keep data in sync with only one connection at a time

SERVICE_SET_AIRCLEANER_MODE = "set_aircleaner_mode"
SERVICE_SET_HUMIDIFY_SETPOINT = "set_humidify_setpoint"
SERVICE_SET_HVAC_RUN_MODE = "set_hvac_run_mode"

SET_AIRCLEANER_SCHEMA = {
    vol.Required(ATTR_AIRCLEANER_MODE): cv.string,
}

SET_HUMIDITY_SCHEMA = {
    vol.Required(ATTR_HUMIDITY): vol.All(vol.Coerce(int), vol.Range(min=35, max=65)),
}

SET_HVAC_RUN_MODE_SCHEMA = vol.All(
    cv.has_at_least_one_key(ATTR_RUN_MODE, ATTR_HVAC_MODE),
    cv.make_entity_service_schema(
        {
            vol.Optional(ATTR_RUN_MODE): vol.In([HOLD_PERMANENT, HOLD_RESUME_SCHEDULE]),
            vol.Optional(ATTR_HVAC_MODE): vol.In(
                [HVACMode.HEAT, HVACMode.COOL, HVACMode.AUTO]
            ),
        }
    ),
)

#
# Nexia has two bits to determine hvac mode
# There are actually eight states so we map to
# the most significant state
#
# 1. Zone Mode : Auto / Cooling / Heating / Off
# 2. Run Mode  : Hold / Run Schedule
#
#
HA_TO_NEXIA_HVAC_MODE_MAP = {
    HVACMode.HEAT: OPERATION_MODE_HEAT,
    HVACMode.COOL: OPERATION_MODE_COOL,
    HVACMode.HEAT_COOL: OPERATION_MODE_AUTO,
    HVACMode.AUTO: OPERATION_MODE_AUTO,
    HVACMode.OFF: OPERATION_MODE_OFF,
}
NEXIA_TO_HA_HVAC_MODE_MAP = {
    value: key for key, value in HA_TO_NEXIA_HVAC_MODE_MAP.items()
}

HVAC_MODES = [
    HVACMode.OFF,
    HVACMode.AUTO,
    HVACMode.HEAT_COOL,
    HVACMode.HEAT,
    HVACMode.COOL,
]

NEXIA_SUPPORTED = (
    ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    | ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.FAN_MODE
    | ClimateEntityFeature.PRESET_MODE
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate for a Nexia device."""
    coordinator: NexiaDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    nexia_home: NexiaHome = coordinator.nexia_home

    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_SET_HUMIDIFY_SETPOINT,
        SET_HUMIDITY_SCHEMA,
        SERVICE_SET_HUMIDIFY_SETPOINT,
    )
    platform.async_register_entity_service(
        SERVICE_SET_AIRCLEANER_MODE, SET_AIRCLEANER_SCHEMA, SERVICE_SET_AIRCLEANER_MODE
    )
    platform.async_register_entity_service(
        SERVICE_SET_HVAC_RUN_MODE, SET_HVAC_RUN_MODE_SCHEMA, SERVICE_SET_HVAC_RUN_MODE
    )

    entities: list[NexiaZone] = []
    for thermostat_id in nexia_home.get_thermostat_ids():
        thermostat: NexiaThermostat = nexia_home.get_thermostat_by_id(thermostat_id)
        for zone_id in thermostat.get_zone_ids():
            zone: NexiaThermostatZone = thermostat.get_zone_by_id(zone_id)
            entities.append(NexiaZone(coordinator, zone))

    async_add_entities(entities)


class NexiaZone(NexiaThermostatZoneEntity, ClimateEntity):
    """Provides Nexia Climate support."""

    def __init__(
        self, coordinator: NexiaDataUpdateCoordinator, zone: NexiaThermostatZone
    ) -> None:
        """Initialize the thermostat."""
        super().__init__(
            coordinator, zone, name=zone.get_name(), unique_id=zone.zone_id
        )
        unit = self._thermostat.get_unit()
        min_humidity, max_humidity = self._thermostat.get_humidity_setpoint_limits()
        min_setpoint, max_setpoint = self._thermostat.get_setpoint_limits()
        # The has_* calls are stable for the life of the device
        # and do not do I/O
        self._has_relative_humidity = self._thermostat.has_relative_humidity()
        self._has_emergency_heat = self._thermostat.has_emergency_heat()
        self._has_humidify_support = self._thermostat.has_humidify_support()
        self._has_dehumidify_support = self._thermostat.has_dehumidify_support()
        supported = NEXIA_SUPPORTED
        if self._has_humidify_support or self._has_dehumidify_support:
            supported |= ClimateEntityFeature.TARGET_HUMIDITY
        if self._has_emergency_heat:
            supported |= ClimateEntityFeature.AUX_HEAT
        self._attr_supported_features = supported
        self._attr_preset_modes = self._zone.get_presets()
        self._attr_fan_modes = self._thermostat.get_fan_modes()
        self._attr_hvac_modes = HVAC_MODES
        self._attr_min_humidity = percent_conv(min_humidity)
        self._attr_max_humidity = percent_conv(max_humidity)
        self._attr_min_temp = min_setpoint
        self._attr_max_temp = max_setpoint
        self._attr_temperature_unit = TEMP_CELSIUS if unit == "C" else TEMP_FAHRENHEIT
        self._attr_target_temperature_step = 0.5 if unit == "C" else 1.0

    @property
    def is_fan_on(self):
        """Blower is on."""
        return self._thermostat.is_blower_active()

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._zone.get_temperature()

    @property
    def fan_mode(self):
        """Return the fan setting."""
        return self._thermostat.get_fan_mode()

    def set_fan_mode(self, fan_mode):
        """Set new target fan mode."""
        self._thermostat.set_fan_mode(fan_mode)
        self._signal_thermostat_update()

    def set_hvac_run_mode(self, run_mode, hvac_mode):
        """Set the hvac run mode."""
        if run_mode is not None:
            if run_mode == HOLD_PERMANENT:
                self._zone.call_permanent_hold()
            else:
                self._zone.call_return_to_schedule()
        if hvac_mode is not None:
            self._zone.set_mode(mode=HA_TO_NEXIA_HVAC_MODE_MAP[hvac_mode])
        self._signal_thermostat_update()

    @property
    def preset_mode(self):
        """Preset that is active."""
        return self._zone.get_preset()

    def set_humidity(self, humidity):
        """Dehumidify target."""
        if self._thermostat.has_dehumidify_support():
            self.set_dehumidify_setpoint(humidity)
        else:
            self.set_humidify_setpoint(humidity)
        self._signal_thermostat_update()

    @property
    def target_humidity(self):
        """Humidity indoors setpoint."""
        if self._has_dehumidify_support:
            return percent_conv(self._thermostat.get_dehumidify_setpoint())
        if self._has_humidify_support:
            return percent_conv(self._thermostat.get_humidify_setpoint())
        return None

    @property
    def current_humidity(self):
        """Humidity indoors."""
        if self._has_relative_humidity:
            return percent_conv(self._thermostat.get_relative_humidity())
        return None

    @property
    def target_temperature(self):
        """Temperature we try to reach."""
        current_mode = self._zone.get_current_mode()

        if current_mode == OPERATION_MODE_COOL:
            return self._zone.get_cooling_setpoint()
        if current_mode == OPERATION_MODE_HEAT:
            return self._zone.get_heating_setpoint()
        return None

    @property
    def target_temperature_high(self):
        """Highest temperature we are trying to reach."""
        current_mode = self._zone.get_current_mode()

        if current_mode in (OPERATION_MODE_COOL, OPERATION_MODE_HEAT):
            return None
        return self._zone.get_cooling_setpoint()

    @property
    def target_temperature_low(self):
        """Lowest temperature we are trying to reach."""
        current_mode = self._zone.get_current_mode()

        if current_mode in (OPERATION_MODE_COOL, OPERATION_MODE_HEAT):
            return None
        return self._zone.get_heating_setpoint()

    @property
    def hvac_action(self) -> HVACAction:
        """Operation ie. heat, cool, idle."""
        system_status = self._thermostat.get_system_status()
        zone_called = self._zone.is_calling()

        if self._zone.get_requested_mode() == OPERATION_MODE_OFF:
            return HVACAction.OFF
        if not zone_called:
            return HVACAction.IDLE
        if system_status == SYSTEM_STATUS_COOL:
            return HVACAction.COOLING
        if system_status == SYSTEM_STATUS_HEAT:
            return HVACAction.HEATING
        if system_status == SYSTEM_STATUS_IDLE:
            return HVACAction.IDLE
        return HVACAction.IDLE

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current mode, as the user-visible name."""
        mode = self._zone.get_requested_mode()
        hold = self._zone.is_in_permanent_hold()

        # If the device is in hold mode with
        # OPERATION_MODE_AUTO
        # overriding the schedule by still
        # heating and cooling to the
        # temp range.
        if hold and mode == OPERATION_MODE_AUTO:
            return HVACMode.HEAT_COOL

        return NEXIA_TO_HA_HVAC_MODE_MAP[mode]

    def set_temperature(self, **kwargs):
        """Set target temperature."""
        new_heat_temp = kwargs.get(ATTR_TARGET_TEMP_LOW)
        new_cool_temp = kwargs.get(ATTR_TARGET_TEMP_HIGH)
        set_temp = kwargs.get(ATTR_TEMPERATURE)

        deadband = self._thermostat.get_deadband()
        cur_cool_temp = self._zone.get_cooling_setpoint()
        cur_heat_temp = self._zone.get_heating_setpoint()
        (min_temp, max_temp) = self._thermostat.get_setpoint_limits()

        # Check that we're not going to hit any minimum or maximum values
        if new_heat_temp and new_heat_temp + deadband > max_temp:
            new_heat_temp = max_temp - deadband
        if new_cool_temp and new_cool_temp - deadband < min_temp:
            new_cool_temp = min_temp + deadband

        # Check that we're within the deadband range, fix it if we're not
        if (
            new_heat_temp
            and new_heat_temp != cur_heat_temp
            and new_cool_temp - new_heat_temp < deadband
        ):
            new_cool_temp = new_heat_temp + deadband

        if (
            new_cool_temp
            and new_cool_temp != cur_cool_temp
            and new_cool_temp - new_heat_temp < deadband
        ):
            new_heat_temp = new_cool_temp - deadband

        self._zone.set_heat_cool_temp(
            heat_temperature=new_heat_temp,
            cool_temperature=new_cool_temp,
            set_temperature=set_temp,
        )
        self._signal_zone_update()

    @property
    def is_aux_heat(self):
        """Emergency heat state."""
        return self._thermostat.is_emergency_heat_active()

    @property
    def extra_state_attributes(self):
        """Return the device specific state attributes."""
        data = super().extra_state_attributes

        data[ATTR_ZONE_STATUS] = self._zone.get_status()

        if not self._has_relative_humidity:
            return data

        data.update(
            {
                ATTR_DEHUMIDIFY_SUPPORTED: self._has_dehumidify_support,
                ATTR_HUMIDIFY_SUPPORTED: self._has_humidify_support,
            }
        )

        if self._has_dehumidify_support:
            dehumdify_setpoint = percent_conv(
                self._thermostat.get_dehumidify_setpoint()
            )
            data[ATTR_DEHUMIDIFY_SETPOINT] = dehumdify_setpoint

        if self._has_humidify_support:
            humdify_setpoint = percent_conv(self._thermostat.get_humidify_setpoint())
            data[ATTR_HUMIDIFY_SETPOINT] = humdify_setpoint

        return data

    def set_preset_mode(self, preset_mode: str):
        """Set the preset mode."""
        self._zone.set_preset(preset_mode)
        self._signal_zone_update()

    def turn_aux_heat_off(self):
        """Turn. Aux Heat off."""
        self._thermostat.set_emergency_heat(False)
        self._signal_thermostat_update()

    def turn_aux_heat_on(self):
        """Turn. Aux Heat on."""
        self._thermostat.set_emergency_heat(True)
        self._signal_thermostat_update()

    def turn_off(self):
        """Turn. off the zone."""
        self.set_hvac_mode(OPERATION_MODE_OFF)
        self._signal_zone_update()

    def turn_on(self):
        """Turn. on the zone."""
        self.set_hvac_mode(OPERATION_MODE_AUTO)
        self._signal_zone_update()

    def set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the system mode (Auto, Heat_Cool, Cool, Heat, etc)."""
        if hvac_mode == HVACMode.AUTO:
            self._zone.call_return_to_schedule()
            self._zone.set_mode(mode=OPERATION_MODE_AUTO)
        else:
            self._zone.call_permanent_hold()
            self._zone.set_mode(mode=HA_TO_NEXIA_HVAC_MODE_MAP[hvac_mode])

        self._signal_zone_update()

    def set_aircleaner_mode(self, aircleaner_mode):
        """Set the aircleaner mode."""
        self._thermostat.set_air_cleaner(aircleaner_mode)
        self._signal_thermostat_update()

    def set_humidify_setpoint(self, humidity):
        """Set the humidify setpoint."""
        target_humidity = find_humidity_setpoint(humidity / 100.0)
        if self._thermostat.get_humidify_setpoint() == target_humidity:
            # Trying to set the humidify setpoint to the
            # same value will cause the api to timeout
            return
        self._thermostat.set_humidify_setpoint(target_humidity)
        self._signal_thermostat_update()

    def set_dehumidify_setpoint(self, humidity):
        """Set the dehumidify setpoint."""
        target_humidity = find_humidity_setpoint(humidity / 100.0)
        if self._thermostat.get_dehumidify_setpoint() == target_humidity:
            # Trying to set the dehumidify setpoint to the
            # same value will cause the api to timeout
            return
        self._thermostat.set_dehumidify_setpoint(target_humidity)
        self._signal_thermostat_update()
