"""Sensor for Xbox Live account status."""
from __future__ import annotations

from datetime import timedelta
import logging

import voluptuous as vol
from xboxapi import Client

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import CONF_API_KEY, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

_LOGGER = logging.getLogger(__name__)

CONF_XUID = "xuid"

ICON = "mdi:microsoft-xbox"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_API_KEY): cv.string,
        vol.Required(CONF_XUID): vol.All(cv.ensure_list, [cv.string]),
    }
)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Xbox platform."""
    api = Client(api_key=config[CONF_API_KEY])
    entities = []

    # request profile info to check api connection
    response = api.api_get("profile")
    if not response.ok:
        _LOGGER.error(
            "Can't setup X API connection. Check your account or "
            "api key on xapi.us. Code: %s Description: %s ",
            response.status_code,
            response.reason,
        )
        return

    users = config[CONF_XUID]

    interval = timedelta(minutes=1 * len(users))
    interval = config.get(CONF_SCAN_INTERVAL, interval)

    for xuid in users:
        if (gamercard := get_user_gamercard(api, xuid)) is None:
            continue
        entities.append(XboxSensor(api, xuid, gamercard, interval))

    if entities:
        add_entities(entities, True)


def get_user_gamercard(api, xuid):
    """Get profile info."""
    gamercard = api.gamer(gamertag="", xuid=xuid).get("gamercard")
    _LOGGER.debug("User gamercard: %s", gamercard)

    if gamercard.get("success", True) and gamercard.get("code") is None:
        return gamercard
    _LOGGER.error(
        "Can't get user profile %s. Error Code: %s Description: %s",
        xuid,
        gamercard.get("code", "unknown"),
        gamercard.get("description", "unknown"),
    )
    return None


class XboxSensor(SensorEntity):
    """A class for the Xbox account."""

    _attr_should_poll = False

    def __init__(self, api, xuid, gamercard, interval):
        """Initialize the sensor."""
        self._state = None
        self._presence = []
        self._xuid = xuid
        self._api = api
        self._gamertag = gamercard["gamertag"]
        self._gamerscore = gamercard["gamerscore"]
        self._interval = interval
        self._picture = gamercard["gamerpicSmallSslImagePath"]
        self._tier = gamercard["tier"]

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._gamertag

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = {"gamerscore": self._gamerscore, "tier": self._tier}

        for device in self._presence:
            for title in device["titles"]:
                attributes[f'{device["type"]} {title["placement"]}'] = title["name"]

        return attributes

    @property
    def entity_picture(self):
        """Avatar of the account."""
        return self._picture

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return ICON

    async def async_added_to_hass(self) -> None:
        """Start custom polling."""

        @callback
        def async_update(event_time=None):
            """Update the entity."""
            self.async_schedule_update_ha_state(True)

        async_track_time_interval(self.hass, async_update, self._interval)

    def update(self) -> None:
        """Update state data from Xbox API."""
        presence = self._api.gamer(gamertag="", xuid=self._xuid).get("presence")
        _LOGGER.debug("User presence: %s", presence)
        self._state = presence["state"]
        self._presence = presence.get("devices", [])
