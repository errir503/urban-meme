"""Reolink integration for HomeAssistant."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging

from aiohttp import ClientConnectorError
import async_timeout
from reolink_aio.exceptions import ApiError, InvalidContentTypeError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .host import ReolinkHost

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CAMERA]
DEVICE_UPDATE_INTERVAL = 60


@dataclass
class ReolinkData:
    """Data for the Reolink integration."""

    host: ReolinkHost
    device_coordinator: DataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up Reolink from a config entry."""
    host = ReolinkHost(hass, config_entry.data, config_entry.options)

    try:
        if not await host.async_init():
            raise ConfigEntryNotReady(
                f"Error while trying to setup {host.api.host}:{host.api.port}: "
                "failed to obtain data from device."
            )
    except (
        ClientConnectorError,
        asyncio.TimeoutError,
        ApiError,
        InvalidContentTypeError,
    ) as err:
        raise ConfigEntryNotReady(
            f'Error while trying to setup {host.api.host}:{host.api.port}: "{str(err)}".'
        ) from err

    config_entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, host.stop)
    )

    async def async_device_config_update():
        """Update the host state cache and renew the ONVIF-subscription."""
        async with async_timeout.timeout(host.api.timeout):
            # Login session is implicitly updated here
            await host.update_states()

    coordinator_device_config_update = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"reolink.{host.api.nvr_name}",
        update_method=async_device_config_update,
        update_interval=timedelta(seconds=DEVICE_UPDATE_INTERVAL),
    )
    # Fetch initial data so we have data when entities subscribe
    await coordinator_device_config_update.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = ReolinkData(
        host=host,
        device_coordinator=coordinator_device_config_update,
    )

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    config_entry.async_on_unload(
        config_entry.add_update_listener(entry_update_listener)
    )

    return True


async def entry_update_listener(hass: HomeAssistant, config_entry: ConfigEntry):
    """Update the configuration of the host entity."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    host: ReolinkHost = hass.data[DOMAIN][config_entry.entry_id].host

    await host.stop()

    if unload_ok := await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    ):
        hass.data[DOMAIN].pop(config_entry.entry_id)

    return unload_ok
