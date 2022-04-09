"""Support for Tado hot water zones."""
import logging

import voluptuous as vol

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, TEMP_CELSIUS
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONST_HVAC_HEAT,
    CONST_MODE_AUTO,
    CONST_MODE_HEAT,
    CONST_MODE_OFF,
    CONST_MODE_SMART_SCHEDULE,
    CONST_OVERLAY_MANUAL,
    CONST_OVERLAY_TADO_MODE,
    CONST_OVERLAY_TIMER,
    DATA,
    DOMAIN,
    SIGNAL_TADO_UPDATE_RECEIVED,
    TYPE_HOT_WATER,
)
from .entity import TadoZoneEntity

_LOGGER = logging.getLogger(__name__)

MODE_AUTO = "auto"
MODE_HEAT = "heat"
MODE_OFF = "off"

OPERATION_MODES = [MODE_AUTO, MODE_HEAT, MODE_OFF]

WATER_HEATER_MAP_TADO = {
    CONST_OVERLAY_MANUAL: MODE_HEAT,
    CONST_OVERLAY_TIMER: MODE_HEAT,
    CONST_OVERLAY_TADO_MODE: MODE_HEAT,
    CONST_HVAC_HEAT: MODE_HEAT,
    CONST_MODE_SMART_SCHEDULE: MODE_AUTO,
    CONST_MODE_OFF: MODE_OFF,
}

SERVICE_WATER_HEATER_TIMER = "set_water_heater_timer"
ATTR_TIME_PERIOD = "time_period"

WATER_HEATER_TIMER_SCHEMA = {
    vol.Required(ATTR_TIME_PERIOD, default="01:00:00"): vol.All(
        cv.time_period, cv.positive_timedelta, lambda td: td.total_seconds()
    ),
    vol.Optional(ATTR_TEMPERATURE): vol.Coerce(float),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Tado water heater platform."""

    tado = hass.data[DOMAIN][entry.entry_id][DATA]
    entities = await hass.async_add_executor_job(_generate_entities, tado)

    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_WATER_HEATER_TIMER,
        WATER_HEATER_TIMER_SCHEMA,
        "set_timer",
    )

    if entities:
        async_add_entities(entities, True)


def _generate_entities(tado):
    """Create all water heater entities."""
    entities = []

    for zone in tado.zones:
        if zone["type"] == TYPE_HOT_WATER:
            entity = create_water_heater_entity(tado, zone["name"], zone["id"], zone)
            entities.append(entity)

    return entities


def create_water_heater_entity(tado, name: str, zone_id: int, zone: str):
    """Create a Tado water heater device."""
    capabilities = tado.get_capabilities(zone_id)

    supports_temperature_control = capabilities["canSetTemperature"]

    if supports_temperature_control and "temperatures" in capabilities:
        temperatures = capabilities["temperatures"]
        min_temp = float(temperatures["celsius"]["min"])
        max_temp = float(temperatures["celsius"]["max"])
    else:
        min_temp = None
        max_temp = None

    entity = TadoWaterHeater(
        tado,
        name,
        zone_id,
        supports_temperature_control,
        min_temp,
        max_temp,
    )

    return entity


class TadoWaterHeater(TadoZoneEntity, WaterHeaterEntity):
    """Representation of a Tado water heater."""

    def __init__(
        self,
        tado,
        zone_name,
        zone_id,
        supports_temperature_control,
        min_temp,
        max_temp,
    ):
        """Initialize of Tado water heater entity."""

        self._tado = tado
        super().__init__(zone_name, tado.home_id, zone_id)

        self.zone_id = zone_id
        self._unique_id = f"{zone_id} {tado.home_id}"

        self._device_is_active = False

        self._supports_temperature_control = supports_temperature_control
        self._min_temperature = min_temp
        self._max_temperature = max_temp

        self._target_temp = None

        self._attr_supported_features = WaterHeaterEntityFeature.OPERATION_MODE
        if self._supports_temperature_control:
            self._attr_supported_features |= WaterHeaterEntityFeature.TARGET_TEMPERATURE

        self._current_tado_hvac_mode = CONST_MODE_SMART_SCHEDULE
        self._overlay_mode = CONST_MODE_SMART_SCHEDULE
        self._tado_zone_data = None

    async def async_added_to_hass(self):
        """Register for sensor updates."""

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_TADO_UPDATE_RECEIVED.format(
                    self._tado.home_id, "zone", self.zone_id
                ),
                self._async_update_callback,
            )
        )
        self._async_update_data()

    @property
    def name(self):
        """Return the name of the entity."""
        return self.zone_name

    @property
    def unique_id(self):
        """Return the unique id."""
        return self._unique_id

    @property
    def current_operation(self):
        """Return current readable operation mode."""
        return WATER_HEATER_MAP_TADO.get(self._current_tado_hvac_mode)

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._tado_zone_data.target_temp

    @property
    def is_away_mode_on(self):
        """Return true if away mode is on."""
        return self._tado_zone_data.is_away

    @property
    def operation_list(self):
        """Return the list of available operation modes (readable)."""
        return OPERATION_MODES

    @property
    def temperature_unit(self):
        """Return the unit of measurement used by the platform."""
        return TEMP_CELSIUS

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self._min_temperature

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self._max_temperature

    def set_operation_mode(self, operation_mode):
        """Set new operation mode."""
        mode = None

        if operation_mode == MODE_OFF:
            mode = CONST_MODE_OFF
        elif operation_mode == MODE_AUTO:
            mode = CONST_MODE_SMART_SCHEDULE
        elif operation_mode == MODE_HEAT:
            mode = CONST_MODE_HEAT

        self._control_heater(hvac_mode=mode)

    def set_timer(self, time_period, temperature=None):
        """Set the timer on the entity, and temperature if supported."""
        if not self._supports_temperature_control and temperature is not None:
            temperature = None

        self._control_heater(
            hvac_mode=CONST_MODE_HEAT, target_temp=temperature, duration=time_period
        )

    def set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if not self._supports_temperature_control or temperature is None:
            return

        if self._current_tado_hvac_mode not in (
            CONST_MODE_OFF,
            CONST_MODE_AUTO,
            CONST_MODE_SMART_SCHEDULE,
        ):
            self._control_heater(target_temp=temperature)
            return

        self._control_heater(target_temp=temperature, hvac_mode=CONST_MODE_HEAT)

    @callback
    def _async_update_callback(self):
        """Load tado data and update state."""
        self._async_update_data()
        self.async_write_ha_state()

    @callback
    def _async_update_data(self):
        """Load tado data."""
        _LOGGER.debug("Updating water_heater platform for zone %d", self.zone_id)
        self._tado_zone_data = self._tado.data["zone"][self.zone_id]
        self._current_tado_hvac_mode = self._tado_zone_data.current_hvac_mode

    def _control_heater(self, hvac_mode=None, target_temp=None, duration=None):
        """Send new target temperature."""

        if hvac_mode:
            self._current_tado_hvac_mode = hvac_mode

        if target_temp:
            self._target_temp = target_temp

        # Set a target temperature if we don't have any
        if self._target_temp is None:
            self._target_temp = self.min_temp

        if self._current_tado_hvac_mode == CONST_MODE_SMART_SCHEDULE:
            _LOGGER.debug(
                "Switching to SMART_SCHEDULE for zone %s (%d)",
                self.zone_name,
                self.zone_id,
            )
            self._tado.reset_zone_overlay(self.zone_id)
            return

        if self._current_tado_hvac_mode == CONST_MODE_OFF:
            _LOGGER.debug(
                "Switching to OFF for zone %s (%d)", self.zone_name, self.zone_id
            )
            self._tado.set_zone_off(self.zone_id, CONST_OVERLAY_MANUAL, TYPE_HOT_WATER)
            return

        overlay_mode = CONST_OVERLAY_MANUAL
        if duration:
            overlay_mode = CONST_OVERLAY_TIMER
        elif self._tado.fallback:
            # Fallback to Smart Schedule at next Schedule switch if we have fallback enabled
            overlay_mode = CONST_OVERLAY_TADO_MODE

        _LOGGER.debug(
            "Switching to %s for zone %s (%d) with temperature %s",
            self._current_tado_hvac_mode,
            self.zone_name,
            self.zone_id,
            self._target_temp,
        )
        self._tado.set_zone_overlay(
            zone_id=self.zone_id,
            overlay_mode=overlay_mode,
            temperature=self._target_temp,
            duration=duration,
            device_type=TYPE_HOT_WATER,
        )
        self._overlay_mode = self._current_tado_hvac_mode
