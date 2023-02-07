"""Provide a mock light platform.

Call init before using it in your tests to ensure clean test data.
"""
from homeassistant.components.light import LightEntity
from homeassistant.const import STATE_OFF, STATE_ON

from tests.common import MockToggleEntity

ENTITIES = []


def init(empty=False):
    """Initialize the platform with entities."""
    global ENTITIES

    ENTITIES = (
        []
        if empty
        else [
            MockLight("Ceiling", STATE_ON),
            MockLight("Ceiling", STATE_OFF),
            MockLight(None, STATE_OFF),
        ]
    )


async def async_setup_platform(
    hass, config, async_add_entities_callback, discovery_info=None
):
    """Return mock entities."""
    async_add_entities_callback(ENTITIES)


class MockLight(MockToggleEntity, LightEntity):
    """Mock light class."""

    color_mode = None
    _attr_max_color_temp_kelvin = 6500
    _attr_min_color_temp_kelvin = 2000
    supported_color_modes = None
    supported_features = 0

    brightness = None
    color_temp_kelvin = None
    hs_color = None
    rgb_color = None
    rgbw_color = None
    rgbww_color = None
    xy_color = None

    def turn_on(self, **kwargs):
        """Turn the entity on."""
        super().turn_on(**kwargs)
        for key, value in kwargs.items():
            if key in [
                "brightness",
                "hs_color",
                "xy_color",
                "rgb_color",
                "rgbw_color",
                "rgbww_color",
                "color_temp_kelvin",
            ]:
                setattr(self, key, value)
            if key == "white":
                setattr(self, "brightness", value)
