"""The sms component."""
import logging

import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_DEVICE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import CONF_BAUD_SPEED, DEFAULT_BAUD_SPEED, DOMAIN, SMS_GATEWAY
from .gateway import create_sms_gateway

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

SMS_CONFIG_SCHEMA = {vol.Required(CONF_DEVICE): cv.isdevice}

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            vol.All(
                cv.deprecated(CONF_DEVICE),
                SMS_CONFIG_SCHEMA,
            ),
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Configure Gammu state machine."""
    hass.data.setdefault(DOMAIN, {})
    if not (sms_config := config.get(DOMAIN, {})):
        return True

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data=sms_config,
        )
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configure Gammu state machine."""

    device = entry.data[CONF_DEVICE]
    connection_mode = "at"
    baud_speed = entry.data.get(CONF_BAUD_SPEED, DEFAULT_BAUD_SPEED)
    if baud_speed != DEFAULT_BAUD_SPEED:
        connection_mode += baud_speed
    config = {"Device": device, "Connection": connection_mode}
    _LOGGER.debug("Connecting mode:%s", connection_mode)
    gateway = await create_sms_gateway(config, hass)
    if not gateway:
        return False
    hass.data[DOMAIN][SMS_GATEWAY] = gateway
    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        gateway = hass.data[DOMAIN].pop(SMS_GATEWAY)
        await gateway.terminate_async()

    return unload_ok
