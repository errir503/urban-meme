"""The Big Ass Fans integration."""
from __future__ import annotations

import asyncio

from aiobafi6 import Device, Service
from aiobafi6.discovery import PORT

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, QUERY_INTERVAL, RUN_TIMEOUT
from .models import BAFData

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.FAN,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Big Ass Fans from a config entry."""
    ip_address = entry.data[CONF_IP_ADDRESS]

    service = Service(ip_addresses=[ip_address], uuid=entry.unique_id, port=PORT)
    device = Device(service, query_interval_seconds=QUERY_INTERVAL)
    run_future = device.async_run()

    try:
        await asyncio.wait_for(device.async_wait_available(), timeout=RUN_TIMEOUT)
    except asyncio.TimeoutError as ex:
        run_future.cancel()
        raise ConfigEntryNotReady(f"Timed out connecting to {ip_address}") from ex

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = BAFData(device, run_future)
    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        data: BAFData = hass.data[DOMAIN].pop(entry.entry_id)
        data.run_future.cancel()

    return unload_ok
