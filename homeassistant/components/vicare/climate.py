"""Viessmann ViCare climate device."""
from __future__ import annotations

from contextlib import suppress
import logging

from PyViCare.PyViCareUtils import (
    PyViCareInvalidDataError,
    PyViCareNotSupportedFeatureError,
    PyViCareRateLimitError,
)
import requests
import voluptuous as vol

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_NONE,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    PRECISION_TENTHS,
    PRECISION_WHOLE,
    TEMP_CELSIUS,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_HEATING_TYPE,
    DOMAIN,
    VICARE_API,
    VICARE_DEVICE_CONFIG,
    VICARE_NAME,
)

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_VICARE_MODE = "set_vicare_mode"
SERVICE_SET_VICARE_MODE_ATTR_MODE = "vicare_mode"

VICARE_MODE_DHW = "dhw"
VICARE_MODE_HEATING = "heating"
VICARE_MODE_DHWANDHEATING = "dhwAndHeating"
VICARE_MODE_DHWANDHEATINGCOOLING = "dhwAndHeatingCooling"
VICARE_MODE_FORCEDREDUCED = "forcedReduced"
VICARE_MODE_FORCEDNORMAL = "forcedNormal"
VICARE_MODE_OFF = "standby"

VICARE_PROGRAM_ACTIVE = "active"
VICARE_PROGRAM_COMFORT = "comfort"
VICARE_PROGRAM_ECO = "eco"
VICARE_PROGRAM_EXTERNAL = "external"
VICARE_PROGRAM_HOLIDAY = "holiday"
VICARE_PROGRAM_NORMAL = "normal"
VICARE_PROGRAM_REDUCED = "reduced"
VICARE_PROGRAM_STANDBY = "standby"

VICARE_HOLD_MODE_AWAY = "away"
VICARE_HOLD_MODE_HOME = "home"
VICARE_HOLD_MODE_OFF = "off"

VICARE_TEMP_HEATING_MIN = 3
VICARE_TEMP_HEATING_MAX = 37

VICARE_TO_HA_HVAC_HEATING = {
    VICARE_MODE_DHW: HVACMode.OFF,
    VICARE_MODE_HEATING: HVACMode.HEAT,
    VICARE_MODE_DHWANDHEATING: HVACMode.AUTO,
    VICARE_MODE_DHWANDHEATINGCOOLING: HVACMode.AUTO,
    VICARE_MODE_FORCEDREDUCED: HVACMode.OFF,
    VICARE_MODE_FORCEDNORMAL: HVACMode.HEAT,
    VICARE_MODE_OFF: HVACMode.OFF,
}

HA_TO_VICARE_HVAC_HEATING = {
    HVACMode.HEAT: VICARE_MODE_FORCEDNORMAL,
    HVACMode.OFF: VICARE_MODE_FORCEDREDUCED,
    HVACMode.AUTO: VICARE_MODE_DHWANDHEATING,
}

VICARE_TO_HA_PRESET_HEATING = {
    VICARE_PROGRAM_COMFORT: PRESET_COMFORT,
    VICARE_PROGRAM_ECO: PRESET_ECO,
    VICARE_PROGRAM_NORMAL: PRESET_NONE,
}

HA_TO_VICARE_PRESET_HEATING = {
    PRESET_COMFORT: VICARE_PROGRAM_COMFORT,
    PRESET_ECO: VICARE_PROGRAM_ECO,
    PRESET_NONE: VICARE_PROGRAM_NORMAL,
}


def _get_circuits(vicare_api):
    """Return the list of circuits."""
    try:
        return vicare_api.circuits
    except PyViCareNotSupportedFeatureError:
        _LOGGER.info("No circuits found")
        return []


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ViCare climate platform."""
    name = VICARE_NAME
    entities = []
    api = hass.data[DOMAIN][config_entry.entry_id][VICARE_API]
    circuits = await hass.async_add_executor_job(_get_circuits, api)

    for circuit in circuits:
        suffix = ""
        if len(circuits) > 1:
            suffix = f" {circuit.id}"

        entity = ViCareClimate(
            f"{name} Heating{suffix}",
            api,
            circuit,
            hass.data[DOMAIN][config_entry.entry_id][VICARE_DEVICE_CONFIG],
            config_entry.data[CONF_HEATING_TYPE],
        )
        entities.append(entity)

    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_SET_VICARE_MODE,
        {vol.Required(SERVICE_SET_VICARE_MODE_ATTR_MODE): cv.string},
        "set_vicare_mode",
    )

    async_add_entities(entities)


class ViCareClimate(ClimateEntity):
    """Representation of the ViCare heating climate device."""

    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
    )

    def __init__(self, name, api, circuit, device_config, heating_type):
        """Initialize the climate device."""
        self._name = name
        self._state = None
        self._api = api
        self._circuit = circuit
        self._device_config = device_config
        self._attributes = {}
        self._target_temperature = None
        self._current_mode = None
        self._current_temperature = None
        self._current_program = None
        self._heating_type = heating_type
        self._current_action = None

    @property
    def unique_id(self):
        """Return unique ID for this device."""
        return f"{self._device_config.getConfig().serial}-{self._circuit.id}"

    @property
    def device_info(self):
        """Return device info for this device."""
        return {
            "identifiers": {(DOMAIN, self._device_config.getConfig().serial)},
            "name": self._device_config.getModel(),
            "manufacturer": "Viessmann",
            "model": (DOMAIN, self._device_config.getModel()),
            "configuration_url": "https://developer.viessmann.com/",
        }

    def update(self):
        """Let HA know there has been an update from the ViCare API."""
        try:
            _room_temperature = None
            with suppress(PyViCareNotSupportedFeatureError):
                _room_temperature = self._circuit.getRoomTemperature()

            _supply_temperature = None
            with suppress(PyViCareNotSupportedFeatureError):
                _supply_temperature = self._circuit.getSupplyTemperature()

            if _room_temperature is not None:
                self._current_temperature = _room_temperature
            elif _supply_temperature is not None:
                self._current_temperature = _supply_temperature
            else:
                self._current_temperature = None

            with suppress(PyViCareNotSupportedFeatureError):
                self._current_program = self._circuit.getActiveProgram()

            with suppress(PyViCareNotSupportedFeatureError):
                self._target_temperature = self._circuit.getCurrentDesiredTemperature()

            with suppress(PyViCareNotSupportedFeatureError):
                self._current_mode = self._circuit.getActiveMode()

            # Update the generic device attributes
            self._attributes = {}

            self._attributes["room_temperature"] = _room_temperature
            self._attributes["active_vicare_program"] = self._current_program
            self._attributes["active_vicare_mode"] = self._current_mode

            with suppress(PyViCareNotSupportedFeatureError):
                self._attributes[
                    "heating_curve_slope"
                ] = self._circuit.getHeatingCurveSlope()

            with suppress(PyViCareNotSupportedFeatureError):
                self._attributes[
                    "heating_curve_shift"
                ] = self._circuit.getHeatingCurveShift()

            self._attributes["vicare_modes"] = self._circuit.getModes()

            self._current_action = False
            # Update the specific device attributes
            with suppress(PyViCareNotSupportedFeatureError):
                for burner in self._api.burners:
                    self._current_action = self._current_action or burner.getActive()

            with suppress(PyViCareNotSupportedFeatureError):
                for compressor in self._api.compressors:
                    self._current_action = (
                        self._current_action or compressor.getActive()
                    )

        except requests.exceptions.ConnectionError:
            _LOGGER.error("Unable to retrieve data from ViCare server")
        except PyViCareRateLimitError as limit_exception:
            _LOGGER.error("Vicare API rate limit exceeded: %s", limit_exception)
        except ValueError:
            _LOGGER.error("Unable to decode data from ViCare server")
        except PyViCareInvalidDataError as invalid_data_exception:
            _LOGGER.error("Invalid data from Vicare server: %s", invalid_data_exception)

    @property
    def name(self):
        """Return the name of the climate device."""
        return self._name

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return TEMP_CELSIUS

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._current_temperature

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temperature

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return current hvac mode."""
        return VICARE_TO_HA_HVAC_HEATING.get(self._current_mode)

    def set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set a new hvac mode on the ViCare API."""
        vicare_mode = HA_TO_VICARE_HVAC_HEATING.get(hvac_mode)
        if vicare_mode is None:
            raise ValueError(
                f"Cannot set invalid vicare mode: {hvac_mode} / {vicare_mode}"
            )

        _LOGGER.debug("Setting hvac mode to %s / %s", hvac_mode, vicare_mode)
        self._circuit.setMode(vicare_mode)

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the list of available hvac modes."""
        return list(HA_TO_VICARE_HVAC_HEATING)

    @property
    def hvac_action(self) -> HVACAction:
        """Return the current hvac action."""
        if self._current_action:
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return VICARE_TEMP_HEATING_MIN

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return VICARE_TEMP_HEATING_MAX

    @property
    def precision(self):
        """Return the precision of the system."""
        return PRECISION_TENTHS

    @property
    def target_temperature_step(self) -> float:
        """Set target temperature step to wholes."""
        return PRECISION_WHOLE

    def set_temperature(self, **kwargs):
        """Set new target temperatures."""
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            self._circuit.setProgramTemperature(self._current_program, temp)
            self._target_temperature = temp

    @property
    def preset_mode(self):
        """Return the current preset mode, e.g., home, away, temp."""
        return VICARE_TO_HA_PRESET_HEATING.get(self._current_program)

    @property
    def preset_modes(self):
        """Return the available preset mode."""
        return list(HA_TO_VICARE_PRESET_HEATING)

    def set_preset_mode(self, preset_mode):
        """Set new preset mode and deactivate any existing programs."""
        vicare_program = HA_TO_VICARE_PRESET_HEATING.get(preset_mode)
        if vicare_program is None:
            raise ValueError(
                f"Cannot set invalid vicare program: {preset_mode}/{vicare_program}"
            )

        _LOGGER.debug("Setting preset to %s / %s", preset_mode, vicare_program)
        if self._current_program != VICARE_PROGRAM_NORMAL:
            # We can't deactivate "normal"
            self._circuit.deactivateProgram(self._current_program)
        if vicare_program != VICARE_PROGRAM_NORMAL:
            # And we can't explicitly activate normal, either
            self._circuit.activateProgram(vicare_program)

    @property
    def extra_state_attributes(self):
        """Show Device Attributes."""
        return self._attributes

    def set_vicare_mode(self, vicare_mode):
        """Service function to set vicare modes directly."""
        if vicare_mode not in self._attributes["vicare_modes"]:
            raise ValueError(f"Cannot set invalid vicare mode: {vicare_mode}.")

        self._circuit.setMode(vicare_mode)
