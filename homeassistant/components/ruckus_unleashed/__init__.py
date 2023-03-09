"""The Ruckus Unleashed integration."""

from pyruckus import Ruckus

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import (
    API_AP,
    API_DEVICE_NAME,
    API_ID,
    API_MAC,
    API_MODEL,
    API_SYSTEM_OVERVIEW,
    API_VERSION,
    COORDINATOR,
    DOMAIN,
    MANUFACTURER,
    PLATFORMS,
    UNDO_UPDATE_LISTENERS,
)
from .coordinator import RuckusUnleashedDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ruckus Unleashed from a config entry."""
    try:
        ruckus = await Ruckus.create(
            entry.data[CONF_HOST],
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
        )
    except ConnectionError as error:
        raise ConfigEntryNotReady from error

    coordinator = RuckusUnleashedDataUpdateCoordinator(hass, ruckus=ruckus)

    await coordinator.async_config_entry_first_refresh()

    system_info = await ruckus.system_info()

    registry = dr.async_get(hass)
    ap_info = await ruckus.ap_info()
    for device in ap_info[API_AP][API_ID].values():
        registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            connections={(dr.CONNECTION_NETWORK_MAC, device[API_MAC])},
            identifiers={(dr.CONNECTION_NETWORK_MAC, device[API_MAC])},
            manufacturer=MANUFACTURER,
            name=device[API_DEVICE_NAME],
            model=device[API_MODEL],
            sw_version=system_info[API_SYSTEM_OVERVIEW][API_VERSION],
        )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        COORDINATOR: coordinator,
        UNDO_UPDATE_LISTENERS: [],
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        for listener in hass.data[DOMAIN][entry.entry_id][UNDO_UPDATE_LISTENERS]:
            listener()

        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
