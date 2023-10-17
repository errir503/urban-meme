"""Reolink integration for HomeAssistant."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Literal

from reolink_aio.api import RETRY_ATTEMPTS
from reolink_aio.exceptions import CredentialsInvalidError, ReolinkError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .exceptions import ReolinkException, UserNotAdmin
from .host import ReolinkHost

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CAMERA,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SIREN,
    Platform.SWITCH,
    Platform.UPDATE,
]
DEVICE_UPDATE_INTERVAL = timedelta(seconds=60)
FIRMWARE_UPDATE_INTERVAL = timedelta(hours=12)


@dataclass
class ReolinkData:
    """Data for the Reolink integration."""

    host: ReolinkHost
    device_coordinator: DataUpdateCoordinator[None]
    firmware_coordinator: DataUpdateCoordinator[str | Literal[False]]


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up Reolink from a config entry."""
    host = ReolinkHost(hass, config_entry.data, config_entry.options)

    try:
        await host.async_init()
    except (UserNotAdmin, CredentialsInvalidError) as err:
        await host.stop()
        raise ConfigEntryAuthFailed(err) from err
    except (
        ReolinkException,
        ReolinkError,
    ) as err:
        await host.stop()
        raise ConfigEntryNotReady(
            f"Error while trying to setup {host.api.host}:{host.api.port}: {str(err)}"
        ) from err
    except Exception:
        await host.stop()
        raise

    config_entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, host.stop)
    )

    starting = True

    async def async_device_config_update() -> None:
        """Update the host state cache and renew the ONVIF-subscription."""
        async with asyncio.timeout(host.api.timeout * (RETRY_ATTEMPTS + 2)):
            try:
                await host.update_states()
            except ReolinkError as err:
                raise UpdateFailed(str(err)) from err

        async with asyncio.timeout(host.api.timeout * (RETRY_ATTEMPTS + 2)):
            await host.renew()

    async def async_check_firmware_update() -> str | Literal[False]:
        """Check for firmware updates."""
        if not host.api.supported(None, "update"):
            return False

        async with asyncio.timeout(host.api.timeout * (RETRY_ATTEMPTS + 2)):
            try:
                return await host.api.check_new_firmware()
            except (ReolinkError, asyncio.exceptions.CancelledError) as err:
                task = asyncio.current_task()
                if task is not None:
                    task.uncancel()
                if starting:
                    _LOGGER.debug(
                        "Error checking Reolink firmware update at startup "
                        "from %s, possibly internet access is blocked",
                        host.api.nvr_name,
                    )
                    return False

                raise UpdateFailed(
                    f"Error checking Reolink firmware update from {host.api.nvr_name}, "
                    "if the camera is blocked from accessing the internet, "
                    "disable the update entity"
                ) from err

    device_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"reolink.{host.api.nvr_name}",
        update_method=async_device_config_update,
        update_interval=DEVICE_UPDATE_INTERVAL,
    )
    firmware_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"reolink.{host.api.nvr_name}.firmware",
        update_method=async_check_firmware_update,
        update_interval=FIRMWARE_UPDATE_INTERVAL,
    )
    # Fetch initial data so we have data when entities subscribe
    try:
        # If camera WAN blocked, firmware check fails, do not prevent setup
        await asyncio.gather(
            device_coordinator.async_config_entry_first_refresh(),
            firmware_coordinator.async_config_entry_first_refresh(),
        )
    except ConfigEntryNotReady:
        await host.stop()
        raise

    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = ReolinkData(
        host=host,
        device_coordinator=device_coordinator,
        firmware_coordinator=firmware_coordinator,
    )

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    config_entry.async_on_unload(
        config_entry.add_update_listener(entry_update_listener)
    )

    starting = False
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
