"""Diagnostics support for Shelly."""
from __future__ import annotations

from typing import Any

from homeassistant.components.bluetooth import async_scanner_by_source
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import format_mac

from .coordinator import get_entry_data

TO_REDACT = {CONF_USERNAME, CONF_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    shelly_entry_data = get_entry_data(hass)[entry.entry_id]

    device_settings: str | dict = "not initialized"
    device_status: str | dict = "not initialized"
    bluetooth: str | dict = "not initialized"
    if shelly_entry_data.block:
        block_coordinator = shelly_entry_data.block
        assert block_coordinator
        device_info = {
            "name": block_coordinator.name,
            "model": block_coordinator.model,
            "sw_version": block_coordinator.sw_version,
        }
        if block_coordinator.device.initialized:
            device_settings = {
                k: v
                for k, v in block_coordinator.device.settings.items()
                if k in ["cloud", "coiot"]
            }
            device_status = {
                k: v
                for k, v in block_coordinator.device.status.items()
                if k
                in [
                    "update",
                    "wifi_sta",
                    "time",
                    "has_update",
                    "ram_total",
                    "ram_free",
                    "ram_lwm",
                    "fs_size",
                    "fs_free",
                    "uptime",
                ]
            }
    else:
        rpc_coordinator = shelly_entry_data.rpc
        assert rpc_coordinator
        device_info = {
            "name": rpc_coordinator.name,
            "model": rpc_coordinator.model,
            "sw_version": rpc_coordinator.sw_version,
        }
        if rpc_coordinator.device.initialized:
            device_settings = {
                k: v for k, v in rpc_coordinator.device.config.items() if k in ["cloud"]
            }
            device_status = {
                k: v
                for k, v in rpc_coordinator.device.status.items()
                if k in ["sys", "wifi"]
            }

        source = format_mac(rpc_coordinator.mac).upper()
        if scanner := async_scanner_by_source(hass, source):
            bluetooth = {
                "scanner": await scanner.async_diagnostics(),
            }

    if isinstance(device_status, dict):
        device_status = async_redact_data(device_status, ["ssid"])

    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "device_info": device_info,
        "device_settings": device_settings,
        "device_status": device_status,
        "bluetooth": bluetooth,
    }
