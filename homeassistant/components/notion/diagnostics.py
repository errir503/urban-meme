"""Diagnostics support for Notion."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_UNIQUE_ID, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

CONF_DEVICE_KEY = "device_key"
CONF_HARDWARE_ID = "hardware_id"
CONF_LAST_BRIDGE_HARDWARE_ID = "last_bridge_hardware_id"
CONF_TITLE = "title"

TO_REDACT = {
    CONF_DEVICE_KEY,
    CONF_EMAIL,
    CONF_HARDWARE_ID,
    CONF_LAST_BRIDGE_HARDWARE_ID,
    CONF_PASSWORD,
    # Config entry title and unique ID may contain sensitive data:
    CONF_TITLE,
    CONF_UNIQUE_ID,
    CONF_USERNAME,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "data": async_redact_data(coordinator.data, TO_REDACT),
    }
