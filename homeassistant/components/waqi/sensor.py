"""Support for the World Air Quality Index service."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

import aiohttp
import voluptuous as vol
from waqiasync import WaqiClient

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_TEMPERATURE,
    ATTR_TIME,
    CONF_TOKEN,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

_LOGGER = logging.getLogger(__name__)

ATTR_DOMINENTPOL = "dominentpol"
ATTR_HUMIDITY = "humidity"
ATTR_NITROGEN_DIOXIDE = "nitrogen_dioxide"
ATTR_OZONE = "ozone"
ATTR_PM10 = "pm_10"
ATTR_PM2_5 = "pm_2_5"
ATTR_PRESSURE = "pressure"
ATTR_SULFUR_DIOXIDE = "sulfur_dioxide"

KEY_TO_ATTR = {
    "pm25": ATTR_PM2_5,
    "pm10": ATTR_PM10,
    "h": ATTR_HUMIDITY,
    "p": ATTR_PRESSURE,
    "t": ATTR_TEMPERATURE,
    "o3": ATTR_OZONE,
    "no2": ATTR_NITROGEN_DIOXIDE,
    "so2": ATTR_SULFUR_DIOXIDE,
}

ATTRIBUTION = "Data provided by the World Air Quality Index project"

ATTR_ICON = "mdi:cloud"

CONF_LOCATIONS = "locations"
CONF_STATIONS = "stations"

SCAN_INTERVAL = timedelta(minutes=5)

TIMEOUT = 10

PLATFORM_SCHEMA = cv.PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_STATIONS): cv.ensure_list,
        vol.Required(CONF_TOKEN): cv.string,
        vol.Required(CONF_LOCATIONS): cv.ensure_list,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the requested World Air Quality Index locations."""

    token = config[CONF_TOKEN]
    station_filter = config.get(CONF_STATIONS)
    locations = config[CONF_LOCATIONS]

    client = WaqiClient(token, async_get_clientsession(hass), timeout=TIMEOUT)
    dev = []
    try:
        for location_name in locations:
            stations = await client.search(location_name)
            _LOGGER.debug("The following stations were returned: %s", stations)
            for station in stations:
                waqi_sensor = WaqiSensor(client, station)
                if not station_filter or {
                    waqi_sensor.uid,
                    waqi_sensor.url,
                    waqi_sensor.station_name,
                } & set(station_filter):
                    dev.append(waqi_sensor)
    except (
        aiohttp.client_exceptions.ClientConnectorError,
        asyncio.TimeoutError,
    ) as err:
        _LOGGER.exception("Failed to connect to WAQI servers")
        raise PlatformNotReady from err
    async_add_entities(dev, True)


class WaqiSensor(SensorEntity):
    """Implementation of a WAQI sensor."""

    _attr_icon = ATTR_ICON
    _attr_device_class = SensorDeviceClass.AQI
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, client, station):
        """Initialize the sensor."""
        self._client = client
        try:
            self.uid = station["uid"]
        except (KeyError, TypeError):
            self.uid = None

        try:
            self.url = station["station"]["url"]
        except (KeyError, TypeError):
            self.url = None

        try:
            self.station_name = station["station"]["name"]
        except (KeyError, TypeError):
            self.station_name = None

        self._data = None

    @property
    def name(self):
        """Return the name of the sensor."""
        if self.station_name:
            return f"WAQI {self.station_name}"
        return f"WAQI {self.url if self.url else self.uid}"

    @property
    def native_value(self):
        """Return the state of the device."""
        if self._data is not None:
            return self._data.get("aqi")
        return None

    @property
    def available(self):
        """Return sensor availability."""
        return self._data is not None

    @property
    def unique_id(self):
        """Return unique ID."""
        return self.uid

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the last update."""
        attrs = {}

        if self._data is not None:
            try:
                attrs[ATTR_ATTRIBUTION] = " and ".join(
                    [ATTRIBUTION]
                    + [v["name"] for v in self._data.get("attributions", [])]
                )

                attrs[ATTR_TIME] = self._data["time"]["s"]
                attrs[ATTR_DOMINENTPOL] = self._data.get("dominentpol")

                iaqi = self._data["iaqi"]
                for key in iaqi:
                    if key in KEY_TO_ATTR:
                        attrs[KEY_TO_ATTR[key]] = iaqi[key]["v"]
                    else:
                        attrs[key] = iaqi[key]["v"]
                return attrs
            except (IndexError, KeyError):
                return {ATTR_ATTRIBUTION: ATTRIBUTION}

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        if self.uid:
            result = await self._client.get_station_by_number(self.uid)
        elif self.url:
            result = await self._client.get_station_by_name(self.url)
        else:
            result = None
        self._data = result
