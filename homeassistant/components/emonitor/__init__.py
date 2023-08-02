"""The SiteSage Emonitor integration."""
from datetime import timedelta
import logging

from aioemonitor import Emonitor

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DEFAULT_UPDATE_RATE = 60

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SiteSage Emonitor from a config entry."""

    session = aiohttp_client.async_get_clientsession(hass)
    emonitor = Emonitor(entry.data[CONF_HOST], session)

    coordinator: DataUpdateCoordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=entry.title,
        update_method=emonitor.async_get_status,
        update_interval=timedelta(seconds=DEFAULT_UPDATE_RATE),
        always_update=False,
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


def name_short_mac(short_mac):
    """Name from short mac."""
    return f"Emonitor {short_mac}"
