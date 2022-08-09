"""The Gree Climate integration."""
from datetime import timedelta
import logging

from homeassistant.components.network import async_get_ipv4_broadcast_addresses
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .bridge import DiscoveryService
from .const import (
    COORDINATORS,
    DATA_DISCOVERY_INTERVAL,
    DATA_DISCOVERY_SERVICE,
    DISCOVERY_SCAN_INTERVAL,
    DISPATCHERS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Gree Climate from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    gree_discovery = DiscoveryService(hass)
    hass.data[DATA_DISCOVERY_SERVICE] = gree_discovery

    hass.data[DOMAIN].setdefault(DISPATCHERS, [])
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _async_scan_update(_=None):
        bcast_addr = list(await async_get_ipv4_broadcast_addresses(hass))
        await gree_discovery.discovery.scan(0, bcast_ifaces=bcast_addr)

    _LOGGER.debug("Scanning network for Gree devices")
    await _async_scan_update()

    hass.data[DOMAIN][DATA_DISCOVERY_INTERVAL] = async_track_time_interval(
        hass, _async_scan_update, timedelta(seconds=DISCOVERY_SCAN_INTERVAL)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if hass.data[DOMAIN].get(DISPATCHERS) is not None:
        for cleanup in hass.data[DOMAIN][DISPATCHERS]:
            cleanup()

    if hass.data[DOMAIN].get(DATA_DISCOVERY_INTERVAL) is not None:
        hass.data[DOMAIN].pop(DATA_DISCOVERY_INTERVAL)()

    if hass.data.get(DATA_DISCOVERY_SERVICE) is not None:
        hass.data.pop(DATA_DISCOVERY_SERVICE)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(COORDINATORS, None)
        hass.data[DOMAIN].pop(DISPATCHERS, None)

    return unload_ok
