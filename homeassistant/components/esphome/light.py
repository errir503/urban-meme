"""Support for ESPHome lights."""
from __future__ import annotations

from typing import Any, cast

from aioesphomeapi import APIVersion, LightColorCapability, LightInfo, LightState

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_EFFECT,
    ATTR_FLASH,
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
    ATTR_RGBWW_COLOR,
    ATTR_TRANSITION,
    ATTR_WHITE,
    FLASH_LONG,
    FLASH_SHORT,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EsphomeEntity, esphome_state_property, platform_async_setup_entry

FLASH_LENGTHS = {FLASH_SHORT: 2, FLASH_LONG: 10}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up ESPHome lights based on a config entry."""
    await platform_async_setup_entry(
        hass,
        entry,
        async_add_entities,
        component_key="light",
        info_type=LightInfo,
        entity_type=EsphomeLight,
        state_type=LightState,
    )


_COLOR_MODE_MAPPING = {
    ColorMode.ONOFF: [
        LightColorCapability.ON_OFF,
    ],
    ColorMode.BRIGHTNESS: [
        LightColorCapability.ON_OFF | LightColorCapability.BRIGHTNESS,
        # for compatibility with older clients (2021.8.x)
        LightColorCapability.BRIGHTNESS,
    ],
    ColorMode.COLOR_TEMP: [
        LightColorCapability.ON_OFF
        | LightColorCapability.BRIGHTNESS
        | LightColorCapability.COLOR_TEMPERATURE,
        LightColorCapability.ON_OFF
        | LightColorCapability.BRIGHTNESS
        | LightColorCapability.COLD_WARM_WHITE,
    ],
    ColorMode.RGB: [
        LightColorCapability.ON_OFF
        | LightColorCapability.BRIGHTNESS
        | LightColorCapability.RGB,
    ],
    ColorMode.RGBW: [
        LightColorCapability.ON_OFF
        | LightColorCapability.BRIGHTNESS
        | LightColorCapability.RGB
        | LightColorCapability.WHITE,
    ],
    ColorMode.RGBWW: [
        LightColorCapability.ON_OFF
        | LightColorCapability.BRIGHTNESS
        | LightColorCapability.RGB
        | LightColorCapability.WHITE
        | LightColorCapability.COLOR_TEMPERATURE,
        LightColorCapability.ON_OFF
        | LightColorCapability.BRIGHTNESS
        | LightColorCapability.RGB
        | LightColorCapability.COLD_WARM_WHITE,
    ],
    ColorMode.WHITE: [
        LightColorCapability.ON_OFF
        | LightColorCapability.BRIGHTNESS
        | LightColorCapability.WHITE
    ],
}


def _color_mode_to_ha(mode: int) -> str:
    """Convert an esphome color mode to a HA color mode constant.

    Choses the color mode that best matches the feature-set.
    """
    candidates = []
    for ha_mode, cap_lists in _COLOR_MODE_MAPPING.items():
        for caps in cap_lists:
            if caps == mode:
                # exact match
                return ha_mode
            if (mode & caps) == caps:
                # all requirements met
                candidates.append((ha_mode, caps))

    if not candidates:
        return ColorMode.UNKNOWN

    # choose the color mode with the most bits set
    candidates.sort(key=lambda key: bin(key[1]).count("1"))
    return candidates[-1][0]


def _filter_color_modes(
    supported: list[int], features: LightColorCapability
) -> list[int]:
    """Filter the given supported color modes, excluding all values that don't have the requested features."""
    return [mode for mode in supported if mode & features]


class EsphomeLight(EsphomeEntity[LightInfo, LightState], LightEntity):
    """A light implementation for ESPHome."""

    @property
    def _supports_color_mode(self) -> bool:
        """Return whether the client supports the new color mode system natively."""
        return self._api_version >= APIVersion(1, 6)

    @property
    @esphome_state_property
    def is_on(self) -> bool | None:
        """Return true if the light is on."""
        return self._state.state

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        data: dict[str, Any] = {"key": self._static_info.key, "state": True}
        # The list of color modes that would fit this service call
        color_modes = self._native_supported_color_modes
        try_keep_current_mode = True

        # rgb/brightness input is in range 0-255, but esphome uses 0-1

        if (brightness_ha := kwargs.get(ATTR_BRIGHTNESS)) is not None:
            data["brightness"] = brightness_ha / 255
            color_modes = _filter_color_modes(
                color_modes, LightColorCapability.BRIGHTNESS
            )

        if (rgb_ha := kwargs.get(ATTR_RGB_COLOR)) is not None:
            rgb = tuple(x / 255 for x in rgb_ha)
            color_bri = max(rgb)
            # normalize rgb
            data["rgb"] = tuple(x / (color_bri or 1) for x in rgb)
            data["color_brightness"] = color_bri
            color_modes = _filter_color_modes(color_modes, LightColorCapability.RGB)
            try_keep_current_mode = False

        if (rgbw_ha := kwargs.get(ATTR_RGBW_COLOR)) is not None:
            # pylint: disable=invalid-name
            *rgb, w = tuple(x / 255 for x in rgbw_ha)  # type: ignore[assignment]
            color_bri = max(rgb)
            # normalize rgb
            data["rgb"] = tuple(x / (color_bri or 1) for x in rgb)
            data["white"] = w
            data["color_brightness"] = color_bri
            color_modes = _filter_color_modes(
                color_modes, LightColorCapability.RGB | LightColorCapability.WHITE
            )
            try_keep_current_mode = False

        if (rgbww_ha := kwargs.get(ATTR_RGBWW_COLOR)) is not None:
            # pylint: disable=invalid-name
            *rgb, cw, ww = tuple(x / 255 for x in rgbww_ha)  # type: ignore[assignment]
            color_bri = max(rgb)
            # normalize rgb
            data["rgb"] = tuple(x / (color_bri or 1) for x in rgb)
            color_modes = _filter_color_modes(color_modes, LightColorCapability.RGB)
            if _filter_color_modes(color_modes, LightColorCapability.COLD_WARM_WHITE):
                # Device supports setting cwww values directly
                data["cold_white"] = cw
                data["warm_white"] = ww
                color_modes = _filter_color_modes(
                    color_modes, LightColorCapability.COLD_WARM_WHITE
                )
            else:
                # need to convert cw+ww part to white+color_temp
                white = data["white"] = max(cw, ww)
                if white != 0:
                    min_ct = self.min_mireds
                    max_ct = self.max_mireds
                    ct_ratio = ww / (cw + ww)
                    data["color_temperature"] = min_ct + ct_ratio * (max_ct - min_ct)
                color_modes = _filter_color_modes(
                    color_modes,
                    LightColorCapability.COLOR_TEMPERATURE | LightColorCapability.WHITE,
                )
            try_keep_current_mode = False

            data["color_brightness"] = color_bri

        if (flash := kwargs.get(ATTR_FLASH)) is not None:
            data["flash_length"] = FLASH_LENGTHS[flash]

        if (transition := kwargs.get(ATTR_TRANSITION)) is not None:
            data["transition_length"] = transition

        if (color_temp := kwargs.get(ATTR_COLOR_TEMP)) is not None:
            data["color_temperature"] = color_temp
            if _filter_color_modes(color_modes, LightColorCapability.COLOR_TEMPERATURE):
                color_modes = _filter_color_modes(
                    color_modes, LightColorCapability.COLOR_TEMPERATURE
                )
            else:
                color_modes = _filter_color_modes(
                    color_modes, LightColorCapability.COLD_WARM_WHITE
                )
            try_keep_current_mode = False

        if (effect := kwargs.get(ATTR_EFFECT)) is not None:
            data["effect"] = effect

        if (white_ha := kwargs.get(ATTR_WHITE)) is not None:
            # ESPHome multiplies brightness and white together for final brightness
            # HA only sends `white` in turn_on, and reads total brightness through brightness property
            data["brightness"] = white_ha / 255
            data["white"] = 1.0
            color_modes = _filter_color_modes(
                color_modes,
                LightColorCapability.BRIGHTNESS | LightColorCapability.WHITE,
            )
            try_keep_current_mode = False

        if self._supports_color_mode and color_modes:
            if (
                try_keep_current_mode
                and self._state is not None
                and self._state.color_mode in color_modes
            ):
                # if possible, stay with the color mode that is already set
                data["color_mode"] = self._state.color_mode
            else:
                # otherwise try the color mode with the least complexity (fewest capabilities set)
                # popcount with bin() function because it appears to be the best way: https://stackoverflow.com/a/9831671
                color_modes.sort(key=lambda mode: bin(mode).count("1"))
                data["color_mode"] = color_modes[0]

        await self._client.light_command(**data)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        data: dict[str, Any] = {"key": self._static_info.key, "state": False}
        if ATTR_FLASH in kwargs:
            data["flash_length"] = FLASH_LENGTHS[kwargs[ATTR_FLASH]]
        if ATTR_TRANSITION in kwargs:
            data["transition_length"] = kwargs[ATTR_TRANSITION]
        await self._client.light_command(**data)

    @property
    @esphome_state_property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255."""
        return round(self._state.brightness * 255)

    @property
    @esphome_state_property
    def color_mode(self) -> str | None:
        """Return the color mode of the light."""
        if not self._supports_color_mode:
            if not (supported := self.supported_color_modes):
                return None
            return next(iter(supported))

        return _color_mode_to_ha(self._state.color_mode)

    @property
    @esphome_state_property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the rgb color value [int, int, int]."""
        if not self._supports_color_mode:
            return (
                round(self._state.red * 255),
                round(self._state.green * 255),
                round(self._state.blue * 255),
            )

        return (
            round(self._state.red * self._state.color_brightness * 255),
            round(self._state.green * self._state.color_brightness * 255),
            round(self._state.blue * self._state.color_brightness * 255),
        )

    @property
    @esphome_state_property
    def rgbw_color(self) -> tuple[int, int, int, int] | None:
        """Return the rgbw color value [int, int, int, int]."""
        white = round(self._state.white * 255)
        rgb = cast("tuple[int, int, int]", self.rgb_color)
        return (*rgb, white)

    @property
    @esphome_state_property
    def rgbww_color(self) -> tuple[int, int, int, int, int] | None:
        """Return the rgbww color value [int, int, int, int, int]."""
        rgb = cast("tuple[int, int, int]", self.rgb_color)
        if not _filter_color_modes(
            self._native_supported_color_modes, LightColorCapability.COLD_WARM_WHITE
        ):
            # Try to reverse white + color temp to cwww
            min_ct = self._static_info.min_mireds
            max_ct = self._static_info.max_mireds
            color_temp = min(max(self._state.color_temperature, min_ct), max_ct)
            white = self._state.white

            ww_frac = (color_temp - min_ct) / (max_ct - min_ct)
            cw_frac = 1 - ww_frac

            return (
                *rgb,
                round(white * cw_frac / max(cw_frac, ww_frac) * 255),
                round(white * ww_frac / max(cw_frac, ww_frac) * 255),
            )
        return (
            *rgb,
            round(self._state.cold_white * 255),
            round(self._state.warm_white * 255),
        )

    @property
    @esphome_state_property
    def color_temp(self) -> float | None:  # type: ignore[override]
        """Return the CT color value in mireds."""
        return self._state.color_temperature

    @property
    @esphome_state_property
    def effect(self) -> str | None:
        """Return the current effect."""
        return self._state.effect

    @property
    def _native_supported_color_modes(self) -> list[int]:
        return self._static_info.supported_color_modes_compat(self._api_version)

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        flags: int = LightEntityFeature.FLASH

        # All color modes except UNKNOWN,ON_OFF support transition
        modes = self._native_supported_color_modes
        if any(m not in (0, LightColorCapability.ON_OFF) for m in modes):
            flags |= LightEntityFeature.TRANSITION
        if self._static_info.effects:
            flags |= LightEntityFeature.EFFECT
        return flags

    @property
    def supported_color_modes(self) -> set[str] | None:
        """Flag supported color modes."""
        supported = set(map(_color_mode_to_ha, self._native_supported_color_modes))
        if ColorMode.ONOFF in supported and len(supported) > 1:
            supported.remove(ColorMode.ONOFF)
        if ColorMode.BRIGHTNESS in supported and len(supported) > 1:
            supported.remove(ColorMode.BRIGHTNESS)
        if ColorMode.WHITE in supported and len(supported) == 1:
            supported.remove(ColorMode.WHITE)
        return supported

    @property
    def effect_list(self) -> list[str]:
        """Return the list of supported effects."""
        return self._static_info.effects

    @property
    def min_mireds(self) -> float:  # type: ignore[override]
        """Return the coldest color_temp that this light supports."""
        return self._static_info.min_mireds

    @property
    def max_mireds(self) -> float:  # type: ignore[override]
        """Return the warmest color_temp that this light supports."""
        return self._static_info.max_mireds
