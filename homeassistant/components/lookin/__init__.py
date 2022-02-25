"""The lookin integration."""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from datetime import timedelta
import logging
from typing import Any

import aiohttp
from aiolookin import (
    Climate,
    LookInHttpProtocol,
    LookinUDPSubscriptions,
    MeteoSensor,
    Remote,
    start_lookin_udp,
)
from aiolookin.models import UDPCommandType, UDPEvent

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, PLATFORMS, TYPE_TO_PLATFORM
from .coordinator import LookinDataUpdateCoordinator, LookinPushCoordinator
from .models import LookinData

LOGGER = logging.getLogger(__name__)

UDP_MANAGER = "udp_manager"


def _async_climate_updater(
    lookin_protocol: LookInHttpProtocol,
    uuid: str,
) -> Callable[[], Coroutine[None, Any, Remote]]:
    """Create a function to capture the cell variable."""

    async def _async_update() -> Climate:
        return await lookin_protocol.get_conditioner(uuid)

    return _async_update


def _async_remote_updater(
    lookin_protocol: LookInHttpProtocol,
    uuid: str,
) -> Callable[[], Coroutine[None, Any, Remote]]:
    """Create a function to capture the cell variable."""

    async def _async_update() -> Remote:
        return await lookin_protocol.get_remote(uuid)

    return _async_update


class LookinUDPManager:
    """Manage the lookin UDP subscriptions."""

    def __init__(self) -> None:
        """Init the manager."""
        self._lock = asyncio.Lock()
        self._listener: Callable | None = None
        self._subscriptions: LookinUDPSubscriptions | None = None

    async def async_get_subscriptions(self) -> LookinUDPSubscriptions:
        """Get the shared LookinUDPSubscriptions."""
        async with self._lock:
            if not self._listener:
                self._subscriptions = LookinUDPSubscriptions()
                self._listener = await start_lookin_udp(self._subscriptions, None)
            return self._subscriptions

    async def async_stop(self) -> None:
        """Stop the listener."""
        async with self._lock:
            assert self._listener is not None
            self._listener()
            self._listener = None
            self._subscriptions = None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up lookin from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    host = entry.data[CONF_HOST]
    lookin_protocol = LookInHttpProtocol(
        api_uri=f"http://{host}", session=async_get_clientsession(hass)
    )

    try:
        lookin_device = await lookin_protocol.get_info()
        devices = await lookin_protocol.get_devices()
    except (asyncio.TimeoutError, aiohttp.ClientError) as ex:
        raise ConfigEntryNotReady from ex

    push_coordinator = LookinPushCoordinator(entry.title)

    meteo_coordinator: LookinDataUpdateCoordinator = LookinDataUpdateCoordinator(
        hass,
        push_coordinator,
        name=entry.title,
        update_method=lookin_protocol.get_meteo_sensor,
        update_interval=timedelta(
            minutes=5
        ),  # Updates are pushed (fallback is polling)
    )
    await meteo_coordinator.async_config_entry_first_refresh()

    device_coordinators: dict[str, LookinDataUpdateCoordinator] = {}
    for remote in devices:
        if (platform := TYPE_TO_PLATFORM.get(remote["Type"])) is None:
            continue
        uuid = remote["UUID"]
        if platform == Platform.CLIMATE:
            updater = _async_climate_updater(lookin_protocol, uuid)
        else:
            updater = _async_remote_updater(lookin_protocol, uuid)
        coordinator = LookinDataUpdateCoordinator(
            hass,
            push_coordinator,
            name=f"{entry.title} {uuid}",
            update_method=updater,
            update_interval=timedelta(
                seconds=60
            ),  # Updates are pushed (fallback is polling)
        )
        await coordinator.async_config_entry_first_refresh()
        device_coordinators[uuid] = coordinator

    @callback
    def _async_meteo_push_update(event: UDPEvent) -> None:
        """Process an update pushed via UDP."""
        LOGGER.debug("Processing push message for meteo sensor: %s", event)
        meteo: MeteoSensor = meteo_coordinator.data
        meteo.update_from_value(event.value)
        meteo_coordinator.async_set_updated_data(meteo)

    if UDP_MANAGER not in domain_data:
        manager = domain_data[UDP_MANAGER] = LookinUDPManager()
    else:
        manager = domain_data[UDP_MANAGER]

    lookin_udp_subs = await manager.async_get_subscriptions()

    entry.async_on_unload(
        lookin_udp_subs.subscribe_event(
            lookin_device.id, UDPCommandType.meteo, None, _async_meteo_push_update
        )
    )

    hass.data[DOMAIN][entry.entry_id] = LookinData(
        host=host,
        lookin_udp_subs=lookin_udp_subs,
        lookin_device=lookin_device,
        meteo_coordinator=meteo_coordinator,
        devices=devices,
        lookin_protocol=lookin_protocol,
        device_coordinators=device_coordinators,
    )

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    loaded_entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state == ConfigEntryState.LOADED
    ]
    if len(loaded_entries) == 1:
        manager: LookinUDPManager = hass.data[DOMAIN][UDP_MANAGER]
        await manager.async_stop()
    return unload_ok
