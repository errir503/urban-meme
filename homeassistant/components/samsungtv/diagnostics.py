"""Diagnostics support for SamsungTV."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant

from .bridge import SamsungTVLegacyBridge, SamsungTVWSBridge
from .const import DOMAIN

TO_REDACT = {CONF_TOKEN}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    bridge: SamsungTVLegacyBridge | SamsungTVWSBridge = hass.data[DOMAIN][
        entry.entry_id
    ]
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "device_info": await bridge.async_device_info(),
    }
