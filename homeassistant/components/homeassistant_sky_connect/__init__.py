"""The Home Assistant Sky Connect integration."""
from __future__ import annotations

import logging

from homeassistant.components import usb
from homeassistant.components.hassio import (
    AddonError,
    AddonInfo,
    AddonManager,
    AddonState,
    is_hassio,
)
from homeassistant.components.homeassistant_hardware.silabs_multiprotocol_addon import (
    get_addon_manager,
    get_zigbee_socket,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .util import get_usb_service_info

_LOGGER = logging.getLogger(__name__)


async def _multi_pan_addon_info(hass, entry: ConfigEntry) -> AddonInfo | None:
    """Return AddonInfo if the multi-PAN addon is enabled for our SkyConnect."""
    if not is_hassio(hass):
        return None

    addon_manager: AddonManager = get_addon_manager(hass)
    try:
        addon_info: AddonInfo = await addon_manager.async_get_addon_info()
    except AddonError as err:
        _LOGGER.error(err)
        raise ConfigEntryNotReady from err

    # Start the addon if it's not started
    if addon_info.state == AddonState.NOT_RUNNING:
        await addon_manager.async_start_addon()

    if addon_info.state not in (AddonState.NOT_INSTALLED, AddonState.RUNNING):
        _LOGGER.debug(
            "Multi pan addon in state %s, delaying yellow config entry setup",
            addon_info.state,
        )
        raise ConfigEntryNotReady

    if addon_info.state == AddonState.NOT_INSTALLED:
        return None

    usb_dev = entry.data["device"]
    dev_path = await hass.async_add_executor_job(usb.get_serial_by_id, usb_dev)

    if addon_info.options["device"] != dev_path:
        return None

    return addon_info


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Home Assistant Sky Connect config entry."""
    matcher = usb.USBCallbackMatcher(
        domain=DOMAIN,
        vid=entry.data["vid"].upper(),
        pid=entry.data["pid"].upper(),
        serial_number=entry.data["serial_number"].lower(),
        manufacturer=entry.data["manufacturer"].lower(),
        description=entry.data["description"].lower(),
    )

    if not usb.async_is_plugged_in(hass, matcher):
        # The USB dongle is not plugged in
        raise ConfigEntryNotReady

    addon_info = await _multi_pan_addon_info(hass, entry)

    if not addon_info:
        usb_info = get_usb_service_info(entry)
        await hass.config_entries.flow.async_init(
            "zha",
            context={"source": "usb"},
            data=usb_info,
        )
        return True

    hw_discovery_data = {
        "name": "Sky Connect Multi-PAN",
        "port": {
            "path": get_zigbee_socket(hass, addon_info),
        },
        "radio_type": "ezsp",
    }
    await hass.config_entries.flow.async_init(
        "zha",
        context={"source": "hardware"},
        data=hw_discovery_data,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return True
