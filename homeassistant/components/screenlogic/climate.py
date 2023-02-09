"""Support for a ScreenLogic heating device."""
import logging
from typing import Any

from screenlogicpy.const import CODE, DATA as SL_DATA, EQUIPMENT, HEAT_MODE

from homeassistant.components.climate import (
    ATTR_PRESET_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import ScreenlogicDataUpdateCoordinator
from .const import DOMAIN
from .entity import ScreenLogicPushEntity

_LOGGER = logging.getLogger(__name__)


SUPPORTED_MODES = [HVACMode.OFF, HVACMode.HEAT]

SUPPORTED_PRESETS = [
    HEAT_MODE.SOLAR,
    HEAT_MODE.SOLAR_PREFERRED,
    HEAT_MODE.HEATER,
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entry."""
    entities = []
    coordinator: ScreenlogicDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    for body in coordinator.gateway_data[SL_DATA.KEY_BODIES]:
        entities.append(ScreenLogicClimate(coordinator, body))

    async_add_entities(entities)


class ScreenLogicClimate(ScreenLogicPushEntity, ClimateEntity, RestoreEntity):
    """Represents a ScreenLogic climate entity."""

    _attr_has_entity_name = True

    _attr_hvac_modes = SUPPORTED_MODES
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
    )

    def __init__(self, coordinator, body):
        """Initialize a ScreenLogic climate entity."""
        super().__init__(coordinator, body, CODE.STATUS_CHANGED)
        self._configured_heat_modes = []
        # Is solar listed as available equipment?
        if self.gateway_data["config"]["equipment_flags"] & EQUIPMENT.FLAG_SOLAR:
            self._configured_heat_modes.extend(
                [HEAT_MODE.SOLAR, HEAT_MODE.SOLAR_PREFERRED]
            )
        self._configured_heat_modes.append(HEAT_MODE.HEATER)
        self._last_preset = None

    @property
    def name(self) -> str:
        """Name of the heater."""
        return self.body["heat_status"]["name"]

    @property
    def min_temp(self) -> float:
        """Minimum allowed temperature."""
        return self.body["min_set_point"]["value"]

    @property
    def max_temp(self) -> float:
        """Maximum allowed temperature."""
        return self.body["max_set_point"]["value"]

    @property
    def current_temperature(self) -> float:
        """Return water temperature."""
        return self.body["last_temperature"]["value"]

    @property
    def target_temperature(self) -> float:
        """Target temperature."""
        return self.body["heat_set_point"]["value"]

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement."""
        if self.config_data["is_celsius"]["value"] == 1:
            return UnitOfTemperature.CELSIUS
        return UnitOfTemperature.FAHRENHEIT

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current hvac mode."""
        if self.body["heat_mode"]["value"] > 0:
            return HVACMode.HEAT
        return HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        """Return the current action of the heater."""
        if self.body["heat_status"]["value"] > 0:
            return HVACAction.HEATING
        if self.hvac_mode == HVACMode.HEAT:
            return HVACAction.IDLE
        return HVACAction.OFF

    @property
    def preset_mode(self) -> str:
        """Return current/last preset mode."""
        if self.hvac_mode == HVACMode.OFF:
            return HEAT_MODE.NAME_FOR_NUM[self._last_preset]
        return HEAT_MODE.NAME_FOR_NUM[self.body["heat_mode"]["value"]]

    @property
    def preset_modes(self) -> list[str]:
        """All available presets."""
        return [
            HEAT_MODE.NAME_FOR_NUM[mode_num] for mode_num in self._configured_heat_modes
        ]

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Change the setpoint of the heater."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            raise ValueError(f"Expected attribute {ATTR_TEMPERATURE}")

        if not await self.gateway.async_set_heat_temp(
            int(self._data_key), int(temperature)
        ):
            raise HomeAssistantError(
                f"Failed to set_temperature {temperature} on body"
                f" {self.body['body_type']['value']}"
            )
        _LOGGER.debug("Set temperature for body %s to %s", self._data_key, temperature)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the operation mode."""
        if hvac_mode == HVACMode.OFF:
            mode = HEAT_MODE.OFF
        else:
            mode = HEAT_MODE.NUM_FOR_NAME[self.preset_mode]

        if not await self.gateway.async_set_heat_mode(int(self._data_key), int(mode)):
            raise HomeAssistantError(
                f"Failed to set_hvac_mode {mode} on body"
                f" {self.body['body_type']['value']}"
            )
        _LOGGER.debug("Set hvac_mode on body %s to %s", self._data_key, mode)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode."""
        _LOGGER.debug("Setting last_preset to %s", HEAT_MODE.NUM_FOR_NAME[preset_mode])
        self._last_preset = mode = HEAT_MODE.NUM_FOR_NAME[preset_mode]
        if self.hvac_mode == HVACMode.OFF:
            return

        if not await self.gateway.async_set_heat_mode(int(self._data_key), int(mode)):
            raise HomeAssistantError(
                f"Failed to set_preset_mode {mode} on body"
                f" {self.body['body_type']['value']}"
            )
        _LOGGER.debug("Set preset_mode on body %s to %s", self._data_key, mode)

    async def async_added_to_hass(self) -> None:
        """Run when entity is about to be added."""
        await super().async_added_to_hass()

        _LOGGER.debug("Startup last preset is %s", self._last_preset)
        if self._last_preset is not None:
            return
        prev_state = await self.async_get_last_state()
        if (
            prev_state is not None
            and prev_state.attributes.get(ATTR_PRESET_MODE) is not None
        ):
            _LOGGER.debug(
                "Startup setting last_preset to %s from prev_state",
                HEAT_MODE.NUM_FOR_NAME[prev_state.attributes.get(ATTR_PRESET_MODE)],
            )
            self._last_preset = HEAT_MODE.NUM_FOR_NAME[
                prev_state.attributes.get(ATTR_PRESET_MODE)
            ]
        else:
            _LOGGER.debug(
                "Startup setting last_preset to default (%s)",
                self._configured_heat_modes[0],
            )
            self._last_preset = self._configured_heat_modes[0]

    @property
    def body(self):
        """Shortcut to access body data."""
        return self.gateway_data[SL_DATA.KEY_BODIES][self._data_key]
