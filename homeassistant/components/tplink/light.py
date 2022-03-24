"""Support for TPLink lights."""
from __future__ import annotations

import logging
from typing import Any, cast

from kasa import SmartBulb, SmartLightStrip

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    ATTR_TRANSITION,
    COLOR_MODE_BRIGHTNESS,
    COLOR_MODE_COLOR_TEMP,
    COLOR_MODE_HS,
    COLOR_MODE_ONOFF,
    SUPPORT_EFFECT,
    SUPPORT_TRANSITION,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.color import (
    color_temperature_kelvin_to_mired as kelvin_to_mired,
    color_temperature_mired_to_kelvin as mired_to_kelvin,
)

from . import legacy_device_id
from .const import DOMAIN
from .coordinator import TPLinkDataUpdateCoordinator
from .entity import CoordinatedTPLinkEntity, async_refresh_after

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches."""
    coordinator: TPLinkDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    if coordinator.device.is_light_strip:
        async_add_entities(
            [
                TPLinkSmartLightStrip(
                    cast(SmartLightStrip, coordinator.device), coordinator
                )
            ]
        )
    elif coordinator.device.is_bulb or coordinator.device.is_dimmer:
        async_add_entities(
            [TPLinkSmartBulb(cast(SmartBulb, coordinator.device), coordinator)]
        )


class TPLinkSmartBulb(CoordinatedTPLinkEntity, LightEntity):
    """Representation of a TPLink Smart Bulb."""

    device: SmartBulb

    def __init__(
        self,
        device: SmartBulb,
        coordinator: TPLinkDataUpdateCoordinator,
    ) -> None:
        """Initialize the switch."""
        super().__init__(device, coordinator)
        # For backwards compat with pyHS100
        if device.is_dimmer:
            # Dimmers used to use the switch format since
            # pyHS100 treated them as SmartPlug but the old code
            # created them as lights
            # https://github.com/home-assistant/core/blob/2021.9.7/homeassistant/components/tplink/common.py#L86
            self._attr_unique_id = legacy_device_id(device)
        else:
            self._attr_unique_id = device.mac.replace(":", "").upper()

    @callback
    def _async_extract_brightness_transition(
        self, **kwargs: Any
    ) -> tuple[int | None, int | None]:
        if (transition := kwargs.get(ATTR_TRANSITION)) is not None:
            transition = int(transition * 1_000)

        if (brightness := kwargs.get(ATTR_BRIGHTNESS)) is not None:
            brightness = round((brightness * 100.0) / 255.0)

        if self.device.is_dimmer and transition is None:
            # This is a stopgap solution for inconsistent set_brightness handling
            # in the upstream library, see #57265.
            # This should be removed when the upstream has fixed the issue.
            # The device logic is to change the settings without turning it on
            # except when transition is defined, so we leverage that here for now.
            transition = 1

        return brightness, transition

    async def _async_set_color_temp(
        self, color_temp_mireds: int, brightness: int | None, transition: int | None
    ) -> None:
        # Handle temp conversion mireds -> kelvin being slightly outside of valid range
        kelvin = mired_to_kelvin(color_temp_mireds)
        kelvin_range = self.device.valid_temperature_range
        color_tmp = max(kelvin_range.min, min(kelvin_range.max, kelvin))
        _LOGGER.debug("Changing color temp to %s", color_tmp)
        await self.device.set_color_temp(
            color_tmp, brightness=brightness, transition=transition
        )

    async def _async_set_hsv(
        self, hs_color: tuple[int, int], brightness: int | None, transition: int | None
    ) -> None:
        # TP-Link requires integers.
        hue, sat = tuple(int(val) for val in hs_color)
        await self.device.set_hsv(hue, sat, brightness, transition=transition)

    async def _async_turn_on_with_brightness(
        self, brightness: int | None, transition: int | None
    ) -> None:
        # Fallback to adjusting brightness or turning the bulb on
        if brightness is not None:
            await self.device.set_brightness(brightness, transition=transition)
            return
        await self.device.turn_on(transition=transition)  # type: ignore[arg-type]

    @async_refresh_after
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        brightness, transition = self._async_extract_brightness_transition(**kwargs)
        if ATTR_COLOR_TEMP in kwargs:
            await self._async_set_color_temp(
                int(kwargs[ATTR_COLOR_TEMP]), brightness, transition
            )
        if ATTR_HS_COLOR in kwargs:
            await self._async_set_hsv(kwargs[ATTR_HS_COLOR], brightness, transition)
        else:
            await self._async_turn_on_with_brightness(brightness, transition)

    @async_refresh_after
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        if (transition := kwargs.get(ATTR_TRANSITION)) is not None:
            transition = int(transition * 1_000)
        await self.device.turn_off(transition=transition)

    @property
    def min_mireds(self) -> int:
        """Return minimum supported color temperature."""
        return kelvin_to_mired(self.device.valid_temperature_range.max)

    @property
    def max_mireds(self) -> int:
        """Return maximum supported color temperature."""
        return kelvin_to_mired(self.device.valid_temperature_range.min)

    @property
    def color_temp(self) -> int | None:
        """Return the color temperature of this light in mireds for HA."""
        return kelvin_to_mired(self.device.color_temp)

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255."""
        return round((self.device.brightness * 255.0) / 100.0)

    @property
    def hs_color(self) -> tuple[int, int] | None:
        """Return the color."""
        hue, saturation, _ = self.device.hsv
        return hue, saturation

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return SUPPORT_TRANSITION

    @property
    def supported_color_modes(self) -> set[str] | None:
        """Return list of available color modes."""
        modes = set()
        if self.device.is_variable_color_temp:
            modes.add(COLOR_MODE_COLOR_TEMP)
        if self.device.is_color:
            modes.add(COLOR_MODE_HS)
        if self.device.is_dimmable:
            modes.add(COLOR_MODE_BRIGHTNESS)

        if not modes:
            modes.add(COLOR_MODE_ONOFF)

        return modes

    @property
    def color_mode(self) -> str | None:
        """Return the active color mode."""
        if self.device.is_color:
            if self.device.is_variable_color_temp and self.device.color_temp:
                return COLOR_MODE_COLOR_TEMP
            return COLOR_MODE_HS
        if self.device.is_variable_color_temp:
            return COLOR_MODE_COLOR_TEMP

        return COLOR_MODE_BRIGHTNESS


class TPLinkSmartLightStrip(TPLinkSmartBulb):
    """Representation of a TPLink Smart Light Strip."""

    device: SmartLightStrip

    def __init__(
        self,
        device: SmartLightStrip,
        coordinator: TPLinkDataUpdateCoordinator,
    ) -> None:
        """Initialize the smart light strip."""
        super().__init__(device, coordinator)

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return super().supported_features | SUPPORT_EFFECT

    @property
    def effect_list(self) -> list[str] | None:
        """Return the list of available effects."""
        if effect_list := self.device.effect_list:
            return cast(list[str], effect_list)
        return None

    @property
    def effect(self) -> str | None:
        """Return the current effect."""
        if (effect := self.device.effect) and effect["enable"]:
            return cast(str, effect["name"])
        return None

    @async_refresh_after
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        brightness, transition = self._async_extract_brightness_transition(**kwargs)
        if ATTR_COLOR_TEMP in kwargs:
            await self._async_set_color_temp(
                int(kwargs[ATTR_COLOR_TEMP]), brightness, transition
            )
        elif ATTR_HS_COLOR in kwargs:
            await self._async_set_hsv(kwargs[ATTR_HS_COLOR], brightness, transition)
        elif ATTR_EFFECT in kwargs:
            await self.device.set_effect(kwargs[ATTR_EFFECT])
        elif (
            self.device.is_off
            and self.device.effect
            and self.device.effect["enable"] == 0
            and self.device.effect["name"]
        ):
            if not self.device.effect["custom"]:
                await self.device.set_effect(self.device.effect["name"])
            # The device does not remember custom effects
            # so we must set a default value or it can never turn back on
            else:
                await self.device.set_hsv(0, 0, 100, transition=transition)
        else:
            await self._async_turn_on_with_brightness(brightness, transition)
