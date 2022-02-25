"""Component to embed Aqualink devices."""
from __future__ import annotations

import asyncio
from functools import wraps
import logging

import aiohttp.client_exceptions
from iaqualink.client import AqualinkClient
from iaqualink.device import (
    AqualinkBinarySensor,
    AqualinkDevice,
    AqualinkLight,
    AqualinkSensor,
    AqualinkThermostat,
    AqualinkToggle,
)
from iaqualink.exception import AqualinkServiceException
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

ATTR_CONFIG = "config"
PARALLEL_UPDATES = 0

PLATFORMS = [
    BINARY_SENSOR_DOMAIN,
    CLIMATE_DOMAIN,
    LIGHT_DOMAIN,
    SENSOR_DOMAIN,
    SWITCH_DOMAIN,
]

CONFIG_SCHEMA = vol.Schema(
    vol.All(
        cv.deprecated(DOMAIN),
        {
            DOMAIN: vol.Schema(
                {
                    vol.Required(CONF_USERNAME): cv.string,
                    vol.Required(CONF_PASSWORD): cv.string,
                }
            )
        },
    ),
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Aqualink component."""
    if (conf := config.get(DOMAIN)) is not None:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_IMPORT},
                data=conf,
            )
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Aqualink from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    hass.data.setdefault(DOMAIN, {})

    # These will contain the initialized devices
    binary_sensors = hass.data[DOMAIN][BINARY_SENSOR_DOMAIN] = []
    climates = hass.data[DOMAIN][CLIMATE_DOMAIN] = []
    lights = hass.data[DOMAIN][LIGHT_DOMAIN] = []
    sensors = hass.data[DOMAIN][SENSOR_DOMAIN] = []
    switches = hass.data[DOMAIN][SWITCH_DOMAIN] = []

    session = async_get_clientsession(hass)
    aqualink = AqualinkClient(username, password, session)
    try:
        await aqualink.login()
    except AqualinkServiceException as login_exception:
        _LOGGER.error("Failed to login: %s", login_exception)
        return False
    except (
        asyncio.TimeoutError,
        aiohttp.client_exceptions.ClientConnectorError,
    ) as aio_exception:
        raise ConfigEntryNotReady(
            f"Error while attempting login: {aio_exception}"
        ) from aio_exception

    try:
        systems = await aqualink.get_systems()
    except AqualinkServiceException as svc_exception:
        raise ConfigEntryNotReady(
            f"Error while attempting to retrieve systems list: {svc_exception}"
        ) from svc_exception

    systems = list(systems.values())
    if not systems:
        _LOGGER.error("No systems detected or supported")
        return False

    # Only supporting the first system for now.
    try:
        devices = await systems[0].get_devices()
    except AqualinkServiceException as svc_exception:
        raise ConfigEntryNotReady(
            f"Error while attempting to retrieve devices list: {svc_exception}"
        ) from svc_exception

    for dev in devices.values():
        if isinstance(dev, AqualinkThermostat):
            climates += [dev]
        elif isinstance(dev, AqualinkLight):
            lights += [dev]
        elif isinstance(dev, AqualinkBinarySensor):
            binary_sensors += [dev]
        elif isinstance(dev, AqualinkSensor):
            sensors += [dev]
        elif isinstance(dev, AqualinkToggle):
            switches += [dev]

    forward_setup = hass.config_entries.async_forward_entry_setup
    if binary_sensors:
        _LOGGER.debug("Got %s binary sensors: %s", len(binary_sensors), binary_sensors)
        hass.async_create_task(forward_setup(entry, Platform.BINARY_SENSOR))
    if climates:
        _LOGGER.debug("Got %s climates: %s", len(climates), climates)
        hass.async_create_task(forward_setup(entry, Platform.CLIMATE))
    if lights:
        _LOGGER.debug("Got %s lights: %s", len(lights), lights)
        hass.async_create_task(forward_setup(entry, Platform.LIGHT))
    if sensors:
        _LOGGER.debug("Got %s sensors: %s", len(sensors), sensors)
        hass.async_create_task(forward_setup(entry, Platform.SENSOR))
    if switches:
        _LOGGER.debug("Got %s switches: %s", len(switches), switches)
        hass.async_create_task(forward_setup(entry, Platform.SWITCH))

    async def _async_systems_update(now):
        """Refresh internal state for all systems."""
        prev = systems[0].online

        try:
            await systems[0].update()
        except AqualinkServiceException as svc_exception:
            if prev is not None:
                _LOGGER.warning("Failed to refresh iAqualink state: %s", svc_exception)
        else:
            cur = systems[0].online
            if cur is True and prev is not True:
                _LOGGER.warning("Reconnected to iAqualink")

        async_dispatcher_send(hass, DOMAIN)

    async_track_time_interval(hass, _async_systems_update, UPDATE_INTERVAL)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    platforms_to_unload = [
        platform for platform in PLATFORMS if platform in hass.data[DOMAIN]
    ]

    del hass.data[DOMAIN]

    return await hass.config_entries.async_unload_platforms(entry, platforms_to_unload)


def refresh_system(func):
    """Force update all entities after state change."""

    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        """Call decorated function and send update signal to all entities."""
        await func(self, *args, **kwargs)
        async_dispatcher_send(self.hass, DOMAIN)

    return wrapper


class AqualinkEntity(Entity):
    """Abstract class for all Aqualink platforms.

    Entity state is updated via the interval timer within the integration.
    Any entity state change via the iaqualink library triggers an internal
    state refresh which is then propagated to all the entities in the system
    via the refresh_system decorator above to the _update_callback in this
    class.
    """

    def __init__(self, dev: AqualinkDevice) -> None:
        """Initialize the entity."""
        self.dev = dev

    async def async_added_to_hass(self) -> None:
        """Set up a listener when this entity is added to HA."""
        self.async_on_remove(
            async_dispatcher_connect(self.hass, DOMAIN, self.async_write_ha_state)
        )

    @property
    def should_poll(self) -> bool:
        """Return False as entities shouldn't be polled.

        Entities are checked periodically as the integration runs periodic
        updates on a timer.
        """
        return False

    @property
    def unique_id(self) -> str:
        """Return a unique identifier for this entity."""
        return f"{self.dev.system.serial}_{self.dev.name}"

    @property
    def assumed_state(self) -> bool:
        """Return whether the state is based on actual reading from the device."""
        return self.dev.system.online in [False, None]

    @property
    def available(self) -> bool:
        """Return whether the device is available or not."""
        return self.dev.system.online is True

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            manufacturer="Jandy",
            model=self.dev.__class__.__name__.replace("Aqualink", ""),
            name=self.name,
            via_device=(DOMAIN, self.dev.system.serial),
        )
