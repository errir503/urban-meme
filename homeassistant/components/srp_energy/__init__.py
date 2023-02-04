"""The SRP Energy integration."""
import logging

from srpenergy.client import SrpEnergyClient

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ID, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import SRP_ENERGY_DOMAIN

_LOGGER = logging.getLogger(__name__)


PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the SRP Energy component from a config entry."""
    # Store an SrpEnergyClient object for your srp_energy to access
    try:
        srp_energy_client = SrpEnergyClient(
            entry.data.get(CONF_ID),
            entry.data.get(CONF_USERNAME),
            entry.data.get(CONF_PASSWORD),
        )
        hass.data[SRP_ENERGY_DOMAIN] = srp_energy_client
    except Exception as ex:
        _LOGGER.error("Unable to connect to Srp Energy: %s", str(ex))
        raise ConfigEntryNotReady from ex

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # unload srp client
    hass.data[SRP_ENERGY_DOMAIN] = None
    # Remove config entry
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
