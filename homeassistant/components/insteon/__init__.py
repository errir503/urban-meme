"""Support for INSTEON Modems (PLM and Hub)."""
import asyncio
from contextlib import suppress
import logging

from pyinsteon import async_close, async_connect, devices
from pyinsteon.constants import ReadWriteMode

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_PLATFORM, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

from . import api
from .const import (
    CONF_CAT,
    CONF_DEV_PATH,
    CONF_DIM_STEPS,
    CONF_HOUSECODE,
    CONF_OVERRIDE,
    CONF_SUBCAT,
    CONF_UNITCODE,
    CONF_X10,
    DOMAIN,
    INSTEON_PLATFORMS,
    ON_OFF_EVENTS,
)
from .schemas import convert_yaml_to_config_flow
from .utils import (
    add_on_off_event_device,
    async_register_services,
    get_device_platforms,
    register_new_device_callback,
)

_LOGGER = logging.getLogger(__name__)
OPTIONS = "options"


async def async_get_device_config(hass, config_entry):
    """Initiate the connection and services."""
    # Make a copy of addresses due to edge case where the list of devices could change during status update
    # Cannot be done concurrently due to issues with the underlying protocol.
    for address in list(devices):
        if devices[address].is_battery:
            continue
        with suppress(AttributeError):
            await devices[address].async_status()

    load_aldb = 2 if devices.modem.aldb.read_write_mode == ReadWriteMode.UNKNOWN else 1
    await devices.async_load(id_devices=1, load_modem_aldb=load_aldb)
    for addr in devices:
        device = devices[addr]
        flags = True
        for name in device.operating_flags:
            if not device.operating_flags[name].is_loaded:
                flags = False
                break
        if flags:
            for name in device.properties:
                if not device.properties[name].is_loaded:
                    flags = False
                    break

        # Cannot be done concurrently due to issues with the underlying protocol.
        if not device.aldb.is_loaded or not flags:
            await device.async_read_config()

    await devices.async_save(workdir=hass.config.config_dir)


async def close_insteon_connection(*args):
    """Close the Insteon connection."""
    await async_close()


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Insteon platform."""
    hass.data[DOMAIN] = {}
    if DOMAIN not in config:
        return True

    conf = dict(config[DOMAIN])
    hass.data[DOMAIN][CONF_DEV_PATH] = conf.pop(CONF_DEV_PATH, None)

    if not conf:
        return True

    data, options = convert_yaml_to_config_flow(conf)

    if options:
        hass.data[DOMAIN][OPTIONS] = options
    # Create a config entry with the connection data
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_IMPORT}, data=data
        )
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up an Insteon entry."""

    if not devices.modem:
        try:
            await async_connect(**entry.data)
        except ConnectionError as exception:
            _LOGGER.error("Could not connect to Insteon modem")
            raise ConfigEntryNotReady from exception

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, close_insteon_connection)
    )

    await devices.async_load(
        workdir=hass.config.config_dir, id_devices=0, load_modem_aldb=0
    )

    # If options existed in YAML and have not already been saved to the config entry
    # add them now
    if (
        not entry.options
        and entry.source == SOURCE_IMPORT
        and hass.data.get(DOMAIN)
        and hass.data[DOMAIN].get(OPTIONS)
    ):
        hass.config_entries.async_update_entry(
            entry=entry,
            options=hass.data[DOMAIN][OPTIONS],
        )

    for device_override in entry.options.get(CONF_OVERRIDE, []):
        # Override the device default capabilities for a specific address
        address = device_override.get("address")
        if not devices.get(address):
            cat = device_override[CONF_CAT]
            subcat = device_override[CONF_SUBCAT]
            devices.set_id(address, cat, subcat, 0)

    for device in entry.options.get(CONF_X10, []):
        housecode = device.get(CONF_HOUSECODE)
        unitcode = device.get(CONF_UNITCODE)
        x10_type = "on_off"
        steps = device.get(CONF_DIM_STEPS, 22)
        if device.get(CONF_PLATFORM) == "light":
            x10_type = "dimmable"
        elif device.get(CONF_PLATFORM) == "binary_sensor":
            x10_type = "sensor"
        _LOGGER.debug(
            "Adding X10 device to Insteon: %s %d %s", housecode, unitcode, x10_type
        )
        device = devices.add_x10_device(housecode, unitcode, x10_type, steps)

    for platform in INSTEON_PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )

    for address in devices:
        device = devices[address]
        platforms = get_device_platforms(device)
        if ON_OFF_EVENTS in platforms:
            add_on_off_event_device(hass, device)
            create_insteon_device(hass, device, entry.entry_id)

    _LOGGER.debug("Insteon device count: %s", len(devices))
    register_new_device_callback(hass)
    async_register_services(hass)

    create_insteon_device(hass, devices.modem, entry.entry_id)

    api.async_load_api(hass)
    await api.async_register_insteon_frontend(hass)

    asyncio.create_task(async_get_device_config(hass, entry))

    return True


def create_insteon_device(hass, device, config_entry_id):
    """Create an Insteon device."""
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=config_entry_id,  # entry.entry_id,
        identifiers={(DOMAIN, str(device.address))},
        manufacturer="SmartLabs, Inc",
        name=f"{device.description} {device.address}",
        model=f"{device.model} ({device.cat!r}, 0x{device.subcat:02x})",
        sw_version=f"{device.firmware:02x} Engine Version: {device.engine_version}",
    )
