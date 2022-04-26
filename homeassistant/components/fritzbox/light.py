"""Support for AVM FRITZ!SmartHome lightbulbs."""
from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import color

from . import FritzBoxEntity
from .const import (
    COLOR_MODE,
    COLOR_TEMP_MODE,
    CONF_COORDINATOR,
    DOMAIN as FRITZBOX_DOMAIN,
)
from .coordinator import FritzboxDataUpdateCoordinator

SUPPORTED_COLOR_MODES = {ColorMode.COLOR_TEMP, ColorMode.HS}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the FRITZ!SmartHome light from ConfigEntry."""
    entities: list[FritzboxLight] = []
    coordinator = hass.data[FRITZBOX_DOMAIN][entry.entry_id][CONF_COORDINATOR]

    for ain, device in coordinator.data.items():
        if not device.has_lightbulb:
            continue

        supported_color_temps = await hass.async_add_executor_job(
            device.get_color_temps
        )

        supported_colors = await hass.async_add_executor_job(device.get_colors)

        entities.append(
            FritzboxLight(
                coordinator,
                ain,
                supported_colors,
                supported_color_temps,
            )
        )

    async_add_entities(entities)


class FritzboxLight(FritzBoxEntity, LightEntity):
    """The light class for FRITZ!SmartHome lightbulbs."""

    def __init__(
        self,
        coordinator: FritzboxDataUpdateCoordinator,
        ain: str,
        supported_colors: dict,
        supported_color_temps: list[str],
    ) -> None:
        """Initialize the FritzboxLight entity."""
        super().__init__(coordinator, ain, None)

        max_kelvin = int(max(supported_color_temps))
        min_kelvin = int(min(supported_color_temps))

        # max kelvin is min mireds and min kelvin is max mireds
        self._attr_min_mireds = color.color_temperature_kelvin_to_mired(max_kelvin)
        self._attr_max_mireds = color.color_temperature_kelvin_to_mired(min_kelvin)

        # Fritz!DECT 500 only supports 12 values for hue, with 3 saturations each.
        # Map supported colors to dict {hue: [sat1, sat2, sat3]} for easier lookup
        self._supported_hs = {}
        for values in supported_colors.values():
            hue = int(values[0][0])
            self._supported_hs[hue] = [
                int(values[0][1]),
                int(values[1][1]),
                int(values[2][1]),
            ]

    @property
    def is_on(self) -> bool:
        """If the light is currently on or off."""
        return self.device.state  # type: ignore [no-any-return]

    @property
    def brightness(self) -> int:
        """Return the current Brightness."""
        return self.device.level  # type: ignore [no-any-return]

    @property
    def hs_color(self) -> tuple[float, float] | None:
        """Return the hs color value."""
        if self.device.color_mode != COLOR_MODE:
            return None

        hue = self.device.hue
        saturation = self.device.saturation

        return (hue, float(saturation) * 100.0 / 255.0)

    @property
    def color_temp(self) -> int | None:
        """Return the CT color value."""
        if self.device.color_mode != COLOR_TEMP_MODE:
            return None

        kelvin = self.device.color_temp
        return color.color_temperature_kelvin_to_mired(kelvin)

    @property
    def supported_color_modes(self) -> set:
        """Flag supported color modes."""
        return SUPPORTED_COLOR_MODES

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        if kwargs.get(ATTR_BRIGHTNESS) is not None:
            level = kwargs[ATTR_BRIGHTNESS]
            await self.hass.async_add_executor_job(self.device.set_level, level)
        if kwargs.get(ATTR_HS_COLOR) is not None:
            hass_hue = int(kwargs[ATTR_HS_COLOR][0])
            hass_saturation = round(kwargs[ATTR_HS_COLOR][1] * 255.0 / 100.0)
            # find supported hs values closest to what user selected
            hue = min(self._supported_hs.keys(), key=lambda x: abs(x - hass_hue))
            saturation = min(
                self._supported_hs[hue], key=lambda x: abs(x - hass_saturation)
            )
            await self.hass.async_add_executor_job(
                self.device.set_color, (hue, saturation)
            )

        if kwargs.get(ATTR_COLOR_TEMP) is not None:
            kelvin = color.color_temperature_kelvin_to_mired(kwargs[ATTR_COLOR_TEMP])
            await self.hass.async_add_executor_job(self.device.set_color_temp, kelvin)

        await self.hass.async_add_executor_job(self.device.set_state_on)
        await self.coordinator.async_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self.hass.async_add_executor_job(self.device.set_state_off)
        await self.coordinator.async_refresh()
