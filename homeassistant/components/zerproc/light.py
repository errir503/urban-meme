"""Zerproc light platform."""
from __future__ import annotations

from datetime import timedelta
import logging

import pyzerproc

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
import homeassistant.util.color as color_util

from .const import DATA_ADDRESSES, DATA_DISCOVERY_SUBSCRIPTION, DOMAIN

_LOGGER = logging.getLogger(__name__)

DISCOVERY_INTERVAL = timedelta(seconds=60)


async def discover_entities(hass: HomeAssistant) -> list[ZerprocLight]:
    """Attempt to discover new lights."""
    lights = await pyzerproc.discover()

    # Filter out already discovered lights
    new_lights = [
        light
        for light in lights
        if light.address not in hass.data[DOMAIN][DATA_ADDRESSES]
    ]

    entities = []
    for light in new_lights:
        hass.data[DOMAIN][DATA_ADDRESSES].add(light.address)
        entities.append(ZerprocLight(light))

    return entities


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Zerproc light devices."""
    warned = False

    async def discover(*args):
        """Wrap discovery to include params."""
        nonlocal warned
        try:
            entities = await discover_entities(hass)
            async_add_entities(entities, update_before_add=True)
            warned = False
        except pyzerproc.ZerprocException:
            if warned is False:
                _LOGGER.warning("Error discovering Zerproc lights", exc_info=True)
                warned = True

    # Initial discovery
    hass.async_create_task(discover())

    # Perform recurring discovery of new devices
    hass.data[DOMAIN][DATA_DISCOVERY_SUBSCRIPTION] = async_track_time_interval(
        hass, discover, DISCOVERY_INTERVAL
    )


class ZerprocLight(LightEntity):
    """Representation of an Zerproc Light."""

    _attr_color_mode = ColorMode.HS
    _attr_supported_color_modes = {ColorMode.HS}

    def __init__(self, light):
        """Initialize a Zerproc light."""
        self._light = light
        self._name = None
        self._is_on = None
        self._hs_color = None
        self._brightness = None
        self._available = True

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        self.async_on_remove(
            self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STOP, self.async_will_remove_from_hass
            )
        )

    async def async_will_remove_from_hass(self, *args) -> None:
        """Run when entity will be removed from hass."""
        try:
            await self._light.disconnect()
        except pyzerproc.ZerprocException:
            _LOGGER.debug(
                "Exception disconnecting from %s", self._light.address, exc_info=True
            )

    @property
    def name(self):
        """Return the display name of this light."""
        return self._light.name

    @property
    def unique_id(self):
        """Return the ID of this light."""
        return self._light.address

    @property
    def device_info(self) -> DeviceInfo:
        """Device info for this light."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            manufacturer="Zerproc",
            name=self.name,
        )

    @property
    def icon(self) -> str | None:
        """Return the icon to use in the frontend."""
        return "mdi:string-lights"

    @property
    def brightness(self):
        """Return the brightness of the light."""
        return self._brightness

    @property
    def hs_color(self):
        """Return the hs color."""
        return self._hs_color

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._is_on

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    async def async_turn_on(self, **kwargs):
        """Instruct the light to turn on."""
        if ATTR_BRIGHTNESS in kwargs or ATTR_HS_COLOR in kwargs:
            default_hs = (0, 0) if self._hs_color is None else self._hs_color
            hue_sat = kwargs.get(ATTR_HS_COLOR, default_hs)

            default_brightness = 255 if self._brightness is None else self._brightness
            brightness = kwargs.get(ATTR_BRIGHTNESS, default_brightness)

            rgb = color_util.color_hsv_to_RGB(*hue_sat, brightness / 255 * 100)
            await self._light.set_color(*rgb)
        else:
            await self._light.turn_on()

    async def async_turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        await self._light.turn_off()

    async def async_update(self):
        """Fetch new state data for this light."""
        try:
            if not self._available:
                await self._light.connect()
            state = await self._light.get_state()
        except pyzerproc.ZerprocException:
            if self._available:
                _LOGGER.warning("Unable to connect to %s", self._light.address)
            self._available = False
            return
        if self._available is False:
            _LOGGER.info("Reconnected to %s", self._light.address)
            self._available = True
        self._is_on = state.is_on
        hsv = color_util.color_RGB_to_hsv(*state.color)
        self._hs_color = hsv[:2]
        self._brightness = int(round((hsv[2] / 100) * 255))
