"""Support for Hive light devices."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.color as color_util

from . import HiveEntity, refresh_system
from .const import ATTR_MODE, DOMAIN

PARALLEL_UPDATES = 0
SCAN_INTERVAL = timedelta(seconds=15)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Hive thermostat based on a config entry."""

    hive = hass.data[DOMAIN][entry.entry_id]
    devices = hive.session.deviceList.get("light")
    entities = []
    if devices:
        for dev in devices:
            entities.append(HiveDeviceLight(hive, dev))
    async_add_entities(entities, True)


class HiveDeviceLight(HiveEntity, LightEntity):
    """Hive Active Light Device."""

    @property
    def unique_id(self):
        """Return unique ID of entity."""
        return self._unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device["device_id"])},
            manufacturer=self.device["deviceData"]["manufacturer"],
            model=self.device["deviceData"]["model"],
            name=self.device["device_name"],
            sw_version=self.device["deviceData"]["version"],
            via_device=(DOMAIN, self.device["parentDevice"]),
        )

    @property
    def name(self):
        """Return the display name of this light."""
        return self.device["haName"]

    @property
    def available(self):
        """Return if the device is available."""
        return self.device["deviceData"]["online"]

    @property
    def extra_state_attributes(self):
        """Show Device Attributes."""
        return {
            ATTR_MODE: self.attributes.get(ATTR_MODE),
        }

    @property
    def brightness(self):
        """Brightness of the light (an integer in the range 1-255)."""
        return self.device["status"]["brightness"]

    @property
    def min_mireds(self):
        """Return the coldest color_temp that this light supports."""
        return self.device.get("min_mireds")

    @property
    def max_mireds(self):
        """Return the warmest color_temp that this light supports."""
        return self.device.get("max_mireds")

    @property
    def color_temp(self):
        """Return the CT color value in mireds."""
        return self.device["status"].get("color_temp")

    @property
    def hs_color(self):
        """Return the hs color value."""
        if self.device["status"]["mode"] == "COLOUR":
            rgb = self.device["status"].get("hs_color")
            return color_util.color_RGB_to_hs(*rgb)
        return None

    @property
    def is_on(self):
        """Return true if light is on."""
        return self.device["status"]["state"]

    @refresh_system
    async def async_turn_on(self, **kwargs):
        """Instruct the light to turn on."""
        new_brightness = None
        new_color_temp = None
        new_color = None
        if ATTR_BRIGHTNESS in kwargs:
            tmp_new_brightness = kwargs.get(ATTR_BRIGHTNESS)
            percentage_brightness = (tmp_new_brightness / 255) * 100
            new_brightness = int(round(percentage_brightness / 5.0) * 5.0)
            if new_brightness == 0:
                new_brightness = 5
        if ATTR_COLOR_TEMP in kwargs:
            tmp_new_color_temp = kwargs.get(ATTR_COLOR_TEMP)
            new_color_temp = round(1000000 / tmp_new_color_temp)
        if ATTR_HS_COLOR in kwargs:
            get_new_color = kwargs.get(ATTR_HS_COLOR)
            hue = int(get_new_color[0])
            saturation = int(get_new_color[1])
            new_color = (hue, saturation, 100)

        await self.hive.light.turnOn(
            self.device, new_brightness, new_color_temp, new_color
        )

    @refresh_system
    async def async_turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        await self.hive.light.turnOff(self.device)

    @property
    def color_mode(self) -> str:
        """Return the color mode of the light."""
        if self.device["hiveType"] == "warmwhitelight":
            return ColorMode.BRIGHTNESS
        if self.device["hiveType"] == "tuneablelight":
            return ColorMode.COLOR_TEMP
        if self.device["hiveType"] == "colourtuneablelight":
            if self.device["status"]["mode"] == "COLOUR":
                return ColorMode.HS
            return ColorMode.COLOR_TEMP
        return ColorMode.ONOFF

    @property
    def supported_color_modes(self) -> set[str] | None:
        """Flag supported color modes."""
        if self.device["hiveType"] == "warmwhitelight":
            return {ColorMode.BRIGHTNESS}
        if self.device["hiveType"] == "tuneablelight":
            return {ColorMode.COLOR_TEMP}
        if self.device["hiveType"] == "colourtuneablelight":
            return {ColorMode.COLOR_TEMP, ColorMode.HS}
        return {ColorMode.ONOFF}

    async def async_update(self):
        """Update all Node data from Hive."""
        await self.hive.session.updateData(self.device)
        self.device = await self.hive.light.getLight(self.device)
        self.attributes.update(self.device.get("attributes", {}))
