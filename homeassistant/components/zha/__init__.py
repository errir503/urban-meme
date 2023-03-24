"""Support for Zigbee Home Automation devices."""
import asyncio
import copy
import logging
import os

import voluptuous as vol
from zhaquirks import setup as setup_quirks
from zigpy.config import CONF_DEVICE, CONF_DEVICE_PATH

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TYPE, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import STORAGE_DIR
from homeassistant.helpers.typing import ConfigType

from . import websocket_api
from .core import ZHAGateway
from .core.const import (
    BAUD_RATES,
    CONF_BAUDRATE,
    CONF_CUSTOM_QUIRKS_PATH,
    CONF_DATABASE,
    CONF_DEVICE_CONFIG,
    CONF_ENABLE_QUIRKS,
    CONF_RADIO_TYPE,
    CONF_USB_PATH,
    CONF_ZIGPY,
    DATA_ZHA,
    DATA_ZHA_CONFIG,
    DATA_ZHA_GATEWAY,
    DATA_ZHA_SHUTDOWN_TASK,
    DOMAIN,
    PLATFORMS,
    SIGNAL_ADD_ENTITIES,
    RadioType,
)
from .core.discovery import GROUP_PROBE

DEVICE_CONFIG_SCHEMA_ENTRY = vol.Schema({vol.Optional(CONF_TYPE): cv.string})
ZHA_CONFIG_SCHEMA = {
    vol.Optional(CONF_BAUDRATE): cv.positive_int,
    vol.Optional(CONF_DATABASE): cv.string,
    vol.Optional(CONF_DEVICE_CONFIG, default={}): vol.Schema(
        {cv.string: DEVICE_CONFIG_SCHEMA_ENTRY}
    ),
    vol.Optional(CONF_ENABLE_QUIRKS, default=True): cv.boolean,
    vol.Optional(CONF_ZIGPY): dict,
    vol.Optional(CONF_RADIO_TYPE): cv.enum(RadioType),
    vol.Optional(CONF_USB_PATH): cv.string,
    vol.Optional(CONF_CUSTOM_QUIRKS_PATH): cv.isdir,
}
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            vol.All(
                cv.deprecated(CONF_USB_PATH),
                cv.deprecated(CONF_BAUDRATE),
                cv.deprecated(CONF_RADIO_TYPE),
                ZHA_CONFIG_SCHEMA,
            ),
        ),
    },
    extra=vol.ALLOW_EXTRA,
)

# Zigbee definitions
CENTICELSIUS = "C-100"

# Internal definitions
_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up ZHA from config."""
    hass.data[DATA_ZHA] = {}

    if DOMAIN in config:
        conf = config[DOMAIN]
        hass.data[DATA_ZHA][DATA_ZHA_CONFIG] = conf

    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up ZHA.

    Will automatically load components to support devices found on the network.
    """

    # Strip whitespace around `socket://` URIs, this is no longer accepted by zigpy
    # This will be removed in 2023.7.0
    path = config_entry.data[CONF_DEVICE][CONF_DEVICE_PATH]
    data = copy.deepcopy(dict(config_entry.data))

    if path.startswith("socket://") and path != path.strip():
        data[CONF_DEVICE][CONF_DEVICE_PATH] = path.strip()
        hass.config_entries.async_update_entry(config_entry, data=data)

    zha_data = hass.data.setdefault(DATA_ZHA, {})
    config = zha_data.get(DATA_ZHA_CONFIG, {})

    for platform in PLATFORMS:
        zha_data.setdefault(platform, [])

    if config.get(CONF_ENABLE_QUIRKS, True):
        setup_quirks(custom_quirks_path=config.get(CONF_CUSTOM_QUIRKS_PATH))

    # temporary code to remove the ZHA storage file from disk.
    # this will be removed in 2022.10.0
    storage_path = hass.config.path(STORAGE_DIR, "zha.storage")
    if os.path.isfile(storage_path):
        _LOGGER.debug("removing ZHA storage file")
        await hass.async_add_executor_job(os.remove, storage_path)
    else:
        _LOGGER.debug("ZHA storage file does not exist or was already removed")

    zha_gateway = ZHAGateway(hass, config, config_entry)
    await zha_gateway.async_initialize()

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={(dr.CONNECTION_ZIGBEE, str(zha_gateway.coordinator_ieee))},
        identifiers={(DOMAIN, str(zha_gateway.coordinator_ieee))},
        name="Zigbee Coordinator",
        manufacturer="ZHA",
        model=zha_gateway.radio_description,
    )

    websocket_api.async_load_api(hass)

    async def async_zha_shutdown(event):
        """Handle shutdown tasks."""
        zha_gateway: ZHAGateway = zha_data[DATA_ZHA_GATEWAY]
        await zha_gateway.shutdown()

    zha_data[DATA_ZHA_SHUTDOWN_TASK] = hass.bus.async_listen_once(
        EVENT_HOMEASSISTANT_STOP, async_zha_shutdown
    )

    await zha_gateway.async_initialize_devices_and_entities()
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    async_dispatcher_send(hass, SIGNAL_ADD_ENTITIES)
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload ZHA config entry."""
    zha_gateway: ZHAGateway = hass.data[DATA_ZHA].pop(DATA_ZHA_GATEWAY)
    await zha_gateway.shutdown()

    GROUP_PROBE.cleanup()
    websocket_api.async_unload_api(hass)

    # our components don't have unload methods so no need to look at return values
    await asyncio.gather(
        *(
            hass.config_entries.async_forward_entry_unload(config_entry, platform)
            for platform in PLATFORMS
        )
    )

    hass.data[DATA_ZHA][DATA_ZHA_SHUTDOWN_TASK]()

    return True


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug("Migrating from version %s", config_entry.version)

    if config_entry.version == 1:
        data = {
            CONF_RADIO_TYPE: config_entry.data[CONF_RADIO_TYPE],
            CONF_DEVICE: {CONF_DEVICE_PATH: config_entry.data[CONF_USB_PATH]},
        }

        baudrate = hass.data[DATA_ZHA].get(DATA_ZHA_CONFIG, {}).get(CONF_BAUDRATE)
        if data[CONF_RADIO_TYPE] != RadioType.deconz and baudrate in BAUD_RATES:
            data[CONF_DEVICE][CONF_BAUDRATE] = baudrate

        config_entry.version = 2
        hass.config_entries.async_update_entry(config_entry, data=data)

    if config_entry.version == 2:
        data = {**config_entry.data}

        if data[CONF_RADIO_TYPE] == "ti_cc":
            data[CONF_RADIO_TYPE] = "znp"

        config_entry.version = 3
        hass.config_entries.async_update_entry(config_entry, data=data)

    _LOGGER.info("Migration to version %s successful", config_entry.version)
    return True
