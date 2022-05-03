"""Light/LED support for the Skybell HD Doorbell."""
from __future__ import annotations

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
import homeassistant.util.color as color_util

from . import DOMAIN as SKYBELL_DOMAIN, SkybellDevice


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the platform for a Skybell device."""
    skybell = hass.data[SKYBELL_DOMAIN]

    sensors = []
    for device in skybell.get_devices():
        sensors.append(SkybellLight(device))

    add_entities(sensors, True)


def _to_skybell_level(level):
    """Convert the given Home Assistant light level (0-255) to Skybell (0-100)."""
    return int((level * 100) / 255)


def _to_hass_level(level):
    """Convert the given Skybell (0-100) light level to Home Assistant (0-255)."""
    return int((level * 255) / 100)


class SkybellLight(SkybellDevice, LightEntity):
    """A binary sensor implementation for Skybell devices."""

    _attr_color_mode = ColorMode.HS
    _attr_supported_color_modes = {ColorMode.HS}

    def __init__(self, device):
        """Initialize a light for a Skybell device."""
        super().__init__(device)
        self._attr_name = device.name

    def turn_on(self, **kwargs):
        """Turn on the light."""
        if ATTR_HS_COLOR in kwargs:
            rgb = color_util.color_hs_to_RGB(*kwargs[ATTR_HS_COLOR])
            self._device.led_rgb = rgb
        elif ATTR_BRIGHTNESS in kwargs:
            self._device.led_intensity = _to_skybell_level(kwargs[ATTR_BRIGHTNESS])
        else:
            self._device.led_intensity = _to_skybell_level(255)

    def turn_off(self, **kwargs):
        """Turn off the light."""
        self._device.led_intensity = 0

    @property
    def is_on(self):
        """Return true if device is on."""
        return self._device.led_intensity > 0

    @property
    def brightness(self):
        """Return the brightness of the light."""
        return _to_hass_level(self._device.led_intensity)

    @property
    def hs_color(self):
        """Return the color of the light."""
        return color_util.color_RGB_to_hs(*self._device.led_rgb)
