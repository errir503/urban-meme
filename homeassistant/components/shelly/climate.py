"""Climate support for Shelly."""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any, cast

from aioshelly.block_device import Block
from aioshelly.exceptions import AuthRequired
import async_timeout

from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, TEMP_CELSIUS
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers import device_registry, entity_registry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import AIOSHELLY_DEVICE_TIMEOUT_SEC, LOGGER, SHTRV_01_TEMPERATURE_SETTINGS
from .coordinator import ShellyBlockCoordinator, get_entry_data
from .utils import get_device_entry_gen


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate device."""

    if get_device_entry_gen(config_entry) == 2:
        return

    coordinator = get_entry_data(hass)[config_entry.entry_id].block
    assert coordinator
    if coordinator.device.initialized:
        async_setup_climate_entities(async_add_entities, coordinator)
    else:
        async_restore_climate_entities(
            hass, config_entry, async_add_entities, coordinator
        )


@callback
def async_setup_climate_entities(
    async_add_entities: AddEntitiesCallback,
    coordinator: ShellyBlockCoordinator,
) -> None:
    """Set up online climate devices."""

    device_block: Block | None = None
    sensor_block: Block | None = None

    assert coordinator.device.blocks

    for block in coordinator.device.blocks:
        if block.type == "device":
            device_block = block
        if hasattr(block, "targetTemp"):
            sensor_block = block

    if sensor_block and device_block:
        LOGGER.debug("Setup online climate device %s", coordinator.name)
        async_add_entities(
            [BlockSleepingClimate(coordinator, sensor_block, device_block)]
        )


@callback
def async_restore_climate_entities(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    coordinator: ShellyBlockCoordinator,
) -> None:
    """Restore sleeping climate devices."""

    ent_reg = entity_registry.async_get(hass)
    entries = entity_registry.async_entries_for_config_entry(
        ent_reg, config_entry.entry_id
    )

    for entry in entries:

        if entry.domain != CLIMATE_DOMAIN:
            continue

        LOGGER.debug("Setup sleeping climate device %s", coordinator.name)
        LOGGER.debug("Found entry %s [%s]", entry.original_name, entry.domain)
        async_add_entities([BlockSleepingClimate(coordinator, None, None, entry)])
        break


class BlockSleepingClimate(
    CoordinatorEntity[ShellyBlockCoordinator], RestoreEntity, ClimateEntity
):
    """Representation of a Shelly climate device."""

    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_icon = "mdi:thermostat"
    _attr_max_temp = SHTRV_01_TEMPERATURE_SETTINGS["max"]
    _attr_min_temp = SHTRV_01_TEMPERATURE_SETTINGS["min"]
    _attr_supported_features: int = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
    )
    _attr_target_temperature_step = SHTRV_01_TEMPERATURE_SETTINGS["step"]
    _attr_temperature_unit = TEMP_CELSIUS

    def __init__(
        self,
        coordinator: ShellyBlockCoordinator,
        sensor_block: Block | None,
        device_block: Block | None,
        entry: entity_registry.RegistryEntry | None = None,
    ) -> None:
        """Initialize climate."""
        super().__init__(coordinator)

        self.block: Block | None = sensor_block
        self.control_result: dict[str, Any] | None = None
        self.device_block: Block | None = device_block
        self.last_state: State | None = None
        self.last_state_attributes: Mapping[str, Any]
        self._preset_modes: list[str] = []
        self._last_target_temp = 20.0

        if self.block is not None and self.device_block is not None:
            self._unique_id = f"{self.coordinator.mac}-{self.block.description}"
            assert self.block.channel
            self._preset_modes = [
                PRESET_NONE,
                *coordinator.device.settings["thermostats"][int(self.block.channel)][
                    "schedule_profile_names"
                ],
            ]
        elif entry is not None:
            self._unique_id = entry.unique_id

        self._channel = cast(int, self._unique_id.split("_")[1])

    @property
    def unique_id(self) -> str:
        """Set unique id of entity."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Name of entity."""
        return self.coordinator.name

    @property
    def target_temperature(self) -> float | None:
        """Set target temperature."""
        if self.block is not None:
            return cast(float, self.block.targetTemp)
        return self.last_state_attributes.get("temperature")

    @property
    def current_temperature(self) -> float | None:
        """Return current temperature."""
        if self.block is not None:
            return cast(float, self.block.temp)
        return self.last_state_attributes.get("current_temperature")

    @property
    def available(self) -> bool:
        """Device availability."""
        if self.device_block is not None:
            return not cast(bool, self.device_block.valveError)
        return self.coordinator.last_update_success

    @property
    def hvac_mode(self) -> HVACMode:
        """HVAC current mode."""
        if self.device_block is None:
            if self.last_state and self.last_state.state in list(HVACMode):
                return HVACMode(self.last_state.state)
            return HVACMode.OFF

        if self.device_block.mode is None or self._check_is_off():
            return HVACMode.OFF

        return HVACMode.HEAT

    @property
    def preset_mode(self) -> str | None:
        """Preset current mode."""
        if self.device_block is None:
            return self.last_state_attributes.get("preset_mode")
        if self.device_block.mode is None:
            return PRESET_NONE
        return self._preset_modes[cast(int, self.device_block.mode)]

    @property
    def hvac_action(self) -> HVACAction:
        """HVAC current action."""
        if (
            self.device_block is None
            or self.device_block.status is None
            or self._check_is_off()
        ):
            return HVACAction.OFF

        return HVACAction.HEATING if bool(self.device_block.status) else HVACAction.IDLE

    @property
    def preset_modes(self) -> list[str]:
        """Preset available modes."""
        return self._preset_modes

    @property
    def device_info(self) -> DeviceInfo:
        """Device info."""
        return {
            "connections": {
                (device_registry.CONNECTION_NETWORK_MAC, self.coordinator.mac)
            }
        }

    def _check_is_off(self) -> bool:
        """Return if valve is off or on."""
        return bool(
            self.target_temperature is None
            or (self.target_temperature <= self._attr_min_temp)
        )

    async def set_state_full_path(self, **kwargs: Any) -> Any:
        """Set block state (HTTP request)."""
        LOGGER.debug("Setting state for entity %s, state: %s", self.name, kwargs)
        try:
            async with async_timeout.timeout(AIOSHELLY_DEVICE_TIMEOUT_SEC):
                return await self.coordinator.device.http_request(
                    "get", f"thermostat/{self._channel}", kwargs
                )
        except (asyncio.TimeoutError, OSError) as err:
            LOGGER.error(
                "Setting state for entity %s failed, state: %s, error: %s",
                self.name,
                kwargs,
                repr(err),
            )
            self.coordinator.last_update_success = False
            return None

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (current_temp := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        await self.set_state_full_path(target_t_enabled=1, target_t=f"{current_temp}")

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set hvac mode."""
        if hvac_mode == HVACMode.OFF:
            if isinstance(self.target_temperature, float):
                self._last_target_temp = self.target_temperature
            await self.set_state_full_path(
                target_t_enabled=1, target_t=f"{self._attr_min_temp}"
            )
        if hvac_mode == HVACMode.HEAT:
            await self.set_state_full_path(
                target_t_enabled=1, target_t=self._last_target_temp
            )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set preset mode."""
        if not self._preset_modes:
            return

        preset_index = self._preset_modes.index(preset_mode)

        if preset_index == 0:
            await self.set_state_full_path(schedule=0)
        else:
            await self.set_state_full_path(
                schedule=1, schedule_profile=f"{preset_index}"
            )

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        LOGGER.info("Restoring entity %s", self.name)

        last_state = await self.async_get_last_state()

        if last_state is not None:
            self.last_state = last_state
            self.last_state_attributes = self.last_state.attributes
            self._preset_modes = cast(
                list, self.last_state.attributes.get("preset_modes")
            )

        await super().async_added_to_hass()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle device update."""
        if not self.coordinator.device.initialized:
            self.async_write_ha_state()
            return

        assert self.coordinator.device.blocks

        for block in self.coordinator.device.blocks:
            if block.type == "device":
                self.device_block = block
            if hasattr(block, "targetTemp"):
                self.block = block

        if self.device_block and self.block:
            LOGGER.debug("Entity %s attached to blocks", self.name)

            assert self.block.channel

            try:
                self._preset_modes = [
                    PRESET_NONE,
                    *self.coordinator.device.settings["thermostats"][
                        int(self.block.channel)
                    ]["schedule_profile_names"],
                ]
            except AuthRequired:
                self.coordinator.entry.async_start_reauth(self.hass)
            else:
                self.async_write_ha_state()
