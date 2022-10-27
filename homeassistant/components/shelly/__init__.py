"""The Shelly integration."""
from __future__ import annotations

from typing import Any, Final

import aioshelly
from aioshelly.block_device import BlockDevice
from aioshelly.exceptions import DeviceConnectionError, InvalidAuthError
from aioshelly.rpc_device import RpcDevice
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import aiohttp_client, device_registry
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.unit_system import METRIC_SYSTEM

from .const import (
    CONF_COAP_PORT,
    CONF_SLEEP_PERIOD,
    DATA_CONFIG_ENTRY,
    DEFAULT_COAP_PORT,
    DOMAIN,
    LOGGER,
)
from .coordinator import (
    ShellyBlockCoordinator,
    ShellyEntryData,
    ShellyRestCoordinator,
    ShellyRpcCoordinator,
    ShellyRpcPollingCoordinator,
    get_entry_data,
)
from .utils import (
    get_block_device_sleep_period,
    get_coap_context,
    get_device_entry_gen,
    get_rpc_device_sleep_period,
    get_ws_context,
)

BLOCK_PLATFORMS: Final = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.COVER,
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]
BLOCK_SLEEPING_PLATFORMS: Final = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SENSOR,
]
RPC_PLATFORMS: Final = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.COVER,
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]
RPC_SLEEPING_PLATFORMS: Final = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
]

COAP_SCHEMA: Final = vol.Schema(
    {
        vol.Optional(CONF_COAP_PORT, default=DEFAULT_COAP_PORT): cv.port,
    }
)
CONFIG_SCHEMA: Final = vol.Schema({DOMAIN: COAP_SCHEMA}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Shelly component."""
    hass.data[DOMAIN] = {DATA_CONFIG_ENTRY: {}}

    if (conf := config.get(DOMAIN)) is not None:
        hass.data[DOMAIN][CONF_COAP_PORT] = conf[CONF_COAP_PORT]

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Shelly from a config entry."""
    # The custom component for Shelly devices uses shelly domain as well as core
    # integration. If the user removes the custom component but doesn't remove the
    # config entry, core integration will try to configure that config entry with an
    # error. The config entry data for this custom component doesn't contain host
    # value, so if host isn't present, config entry will not be configured.
    if not entry.data.get(CONF_HOST):
        LOGGER.warning(
            "The config entry %s probably comes from a custom integration, please remove it if you want to use core Shelly integration",
            entry.title,
        )
        return False

    get_entry_data(hass)[entry.entry_id] = ShellyEntryData()

    if get_device_entry_gen(entry) == 2:
        return await _async_setup_rpc_entry(hass, entry)

    return await _async_setup_block_entry(hass, entry)


async def _async_setup_block_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Shelly block based device from a config entry."""
    temperature_unit = "C" if hass.config.units is METRIC_SYSTEM else "F"

    options = aioshelly.common.ConnectionOptions(
        entry.data[CONF_HOST],
        entry.data.get(CONF_USERNAME),
        entry.data.get(CONF_PASSWORD),
        temperature_unit,
    )

    coap_context = await get_coap_context(hass)

    device = await BlockDevice.create(
        aiohttp_client.async_get_clientsession(hass),
        coap_context,
        options,
        False,
    )

    dev_reg = device_registry.async_get(hass)
    device_entry = None
    if entry.unique_id is not None:
        device_entry = dev_reg.async_get_device(
            identifiers=set(),
            connections={
                (
                    device_registry.CONNECTION_NETWORK_MAC,
                    device_registry.format_mac(entry.unique_id),
                )
            },
        )
    # https://github.com/home-assistant/core/pull/48076
    if device_entry and entry.entry_id not in device_entry.config_entries:
        device_entry = None

    sleep_period = entry.data.get(CONF_SLEEP_PERIOD)
    shelly_entry_data = get_entry_data(hass)[entry.entry_id]

    @callback
    def _async_block_device_setup() -> None:
        """Set up a block based device that is online."""
        shelly_entry_data.block = ShellyBlockCoordinator(hass, entry, device)
        shelly_entry_data.block.async_setup()

        platforms = BLOCK_SLEEPING_PLATFORMS

        if not entry.data.get(CONF_SLEEP_PERIOD):
            shelly_entry_data.rest = ShellyRestCoordinator(hass, device, entry)
            platforms = BLOCK_PLATFORMS

        hass.config_entries.async_setup_platforms(entry, platforms)

    @callback
    def _async_device_online(_: Any) -> None:
        LOGGER.debug("Device %s is online, resuming setup", entry.title)
        shelly_entry_data.device = None

        if sleep_period is None:
            data = {**entry.data}
            data[CONF_SLEEP_PERIOD] = get_block_device_sleep_period(device.settings)
            data["model"] = device.settings["device"]["type"]
            hass.config_entries.async_update_entry(entry, data=data)

        _async_block_device_setup()

    if sleep_period == 0:
        # Not a sleeping device, finish setup
        LOGGER.debug("Setting up online block device %s", entry.title)
        try:
            await device.initialize()
        except DeviceConnectionError as err:
            raise ConfigEntryNotReady(repr(err)) from err
        except InvalidAuthError as err:
            raise ConfigEntryAuthFailed(repr(err)) from err

        _async_block_device_setup()
    elif sleep_period is None or device_entry is None:
        # Need to get sleep info or first time sleeping device setup, wait for device
        shelly_entry_data.device = device
        LOGGER.debug(
            "Setup for device %s will resume when device is online", entry.title
        )
        device.subscribe_updates(_async_device_online)
    else:
        # Restore sensors for sleeping device
        LOGGER.debug("Setting up offline block device %s", entry.title)
        _async_block_device_setup()

    return True


async def _async_setup_rpc_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Shelly RPC based device from a config entry."""
    options = aioshelly.common.ConnectionOptions(
        entry.data[CONF_HOST],
        entry.data.get(CONF_USERNAME),
        entry.data.get(CONF_PASSWORD),
    )

    ws_context = await get_ws_context(hass)

    device = await RpcDevice.create(
        aiohttp_client.async_get_clientsession(hass),
        ws_context,
        options,
        False,
    )

    dev_reg = device_registry.async_get(hass)
    device_entry = None
    if entry.unique_id is not None:
        device_entry = dev_reg.async_get_device(
            identifiers=set(),
            connections={
                (
                    device_registry.CONNECTION_NETWORK_MAC,
                    device_registry.format_mac(entry.unique_id),
                )
            },
        )
    # https://github.com/home-assistant/core/pull/48076
    if device_entry and entry.entry_id not in device_entry.config_entries:
        device_entry = None

    sleep_period = entry.data.get(CONF_SLEEP_PERIOD)
    shelly_entry_data = get_entry_data(hass)[entry.entry_id]

    @callback
    def _async_rpc_device_setup() -> None:
        """Set up a RPC based device that is online."""
        shelly_entry_data.rpc = ShellyRpcCoordinator(hass, entry, device)
        shelly_entry_data.rpc.async_setup()

        platforms = RPC_SLEEPING_PLATFORMS

        if not entry.data.get(CONF_SLEEP_PERIOD):
            shelly_entry_data.rpc_poll = ShellyRpcPollingCoordinator(
                hass, entry, device
            )
            platforms = RPC_PLATFORMS

        hass.config_entries.async_setup_platforms(entry, platforms)

    @callback
    def _async_device_online(_: Any) -> None:
        LOGGER.debug("Device %s is online, resuming setup", entry.title)
        shelly_entry_data.device = None

        if sleep_period is None:
            data = {**entry.data}
            data[CONF_SLEEP_PERIOD] = get_rpc_device_sleep_period(device.config)
            hass.config_entries.async_update_entry(entry, data=data)

        _async_rpc_device_setup()

    if sleep_period == 0:
        # Not a sleeping device, finish setup
        LOGGER.debug("Setting up online RPC device %s", entry.title)
        try:
            await device.initialize()
        except DeviceConnectionError as err:
            raise ConfigEntryNotReady(repr(err)) from err
        except InvalidAuthError as err:
            raise ConfigEntryAuthFailed(repr(err)) from err

        _async_rpc_device_setup()
    elif sleep_period is None or device_entry is None:
        # Need to get sleep info or first time sleeping device setup, wait for device
        shelly_entry_data.device = device
        LOGGER.debug(
            "Setup for device %s will resume when device is online", entry.title
        )
        device.subscribe_updates(_async_device_online)
    else:
        # Restore sensors for sleeping device
        LOGGER.debug("Setting up offline block device %s", entry.title)
        _async_rpc_device_setup()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    shelly_entry_data = get_entry_data(hass)[entry.entry_id]

    # If device is present, block/rpc coordinator is not setup yet
    device = shelly_entry_data.device
    if isinstance(device, RpcDevice):
        await device.shutdown()
        return True
    if isinstance(device, BlockDevice):
        device.shutdown()
        return True

    platforms = RPC_SLEEPING_PLATFORMS
    if not entry.data.get(CONF_SLEEP_PERIOD):
        platforms = RPC_PLATFORMS

    if get_device_entry_gen(entry) == 2:
        if unload_ok := await hass.config_entries.async_unload_platforms(
            entry, platforms
        ):
            if shelly_entry_data.rpc:
                await shelly_entry_data.rpc.shutdown()
            get_entry_data(hass).pop(entry.entry_id)

        return unload_ok

    platforms = BLOCK_SLEEPING_PLATFORMS

    if not entry.data.get(CONF_SLEEP_PERIOD):
        shelly_entry_data.rest = None
        platforms = BLOCK_PLATFORMS

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, platforms):
        if shelly_entry_data.block:
            shelly_entry_data.block.shutdown()
        get_entry_data(hass).pop(entry.entry_id)

    return unload_ok
