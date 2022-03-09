"""Config flow for UPNP."""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import timedelta
from typing import Any, cast

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import ssdp
from homeassistant.components.ssdp import SsdpChange, SsdpServiceInfo
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONFIG_ENTRY_HOSTNAME,
    CONFIG_ENTRY_SCAN_INTERVAL,
    CONFIG_ENTRY_ST,
    CONFIG_ENTRY_UDN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
    SSDP_SEARCH_TIMEOUT,
    ST_IGD_V1,
    ST_IGD_V2,
)


def _friendly_name_from_discovery(discovery_info: ssdp.SsdpServiceInfo) -> str:
    """Extract user-friendly name from discovery."""
    return cast(
        str,
        discovery_info.upnp.get(ssdp.ATTR_UPNP_FRIENDLY_NAME)
        or discovery_info.upnp.get(ssdp.ATTR_UPNP_MODEL_NAME)
        or discovery_info.ssdp_headers.get("_host", ""),
    )


def _is_complete_discovery(discovery_info: ssdp.SsdpServiceInfo) -> bool:
    """Test if discovery is complete and usable."""
    return bool(
        ssdp.ATTR_UPNP_UDN in discovery_info.upnp
        and discovery_info.ssdp_st
        and discovery_info.ssdp_location
        and discovery_info.ssdp_usn
    )


async def _async_wait_for_discoveries(hass: HomeAssistant) -> bool:
    """Wait for a device to be discovered."""
    device_discovered_event = asyncio.Event()

    async def device_discovered(info: SsdpServiceInfo, change: SsdpChange) -> None:
        if change == SsdpChange.BYEBYE:
            return

        LOGGER.info(
            "Device discovered: %s, at: %s",
            info.ssdp_usn,
            info.ssdp_location,
        )
        device_discovered_event.set()

    cancel_discovered_callback_1 = await ssdp.async_register_callback(
        hass,
        device_discovered,
        {
            ssdp.ATTR_SSDP_ST: ST_IGD_V1,
        },
    )
    cancel_discovered_callback_2 = await ssdp.async_register_callback(
        hass,
        device_discovered,
        {
            ssdp.ATTR_SSDP_ST: ST_IGD_V2,
        },
    )

    try:
        await asyncio.wait_for(
            device_discovered_event.wait(), timeout=SSDP_SEARCH_TIMEOUT
        )
    except asyncio.TimeoutError:
        return False
    finally:
        cancel_discovered_callback_1()
        cancel_discovered_callback_2()

    return True


async def _async_discover_igd_devices(
    hass: HomeAssistant,
) -> list[ssdp.SsdpServiceInfo]:
    """Discovery IGD devices."""
    return await ssdp.async_get_discovery_info_by_st(
        hass, ST_IGD_V1
    ) + await ssdp.async_get_discovery_info_by_st(hass, ST_IGD_V2)


class UpnpFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a UPnP/IGD config flow."""

    VERSION = 1

    # Paths:
    # - ssdp(discovery_info) --> ssdp_confirm(None) --> ssdp_confirm({}) --> create_entry()
    # - user(None): scan --> user({...}) --> create_entry()
    # - import(None) --> create_entry()

    def __init__(self) -> None:
        """Initialize the UPnP/IGD config flow."""
        self._discoveries: list[SsdpServiceInfo] | None = None

    async def async_step_user(self, user_input: Mapping | None = None) -> FlowResult:
        """Handle a flow start."""
        LOGGER.debug("async_step_user: user_input: %s", user_input)

        if user_input is not None:
            # Ensure wanted device was discovered.
            assert self._discoveries
            matching_discoveries = [
                discovery
                for discovery in self._discoveries
                if discovery.ssdp_usn == user_input["unique_id"]
            ]
            if not matching_discoveries:
                return self.async_abort(reason="no_devices_found")

            discovery = matching_discoveries[0]
            await self.async_set_unique_id(discovery.ssdp_usn, raise_on_progress=False)
            return await self._async_create_entry_from_discovery(discovery)

        # Discover devices.
        discoveries = await _async_discover_igd_devices(self.hass)

        # Store discoveries which have not been configured.
        current_unique_ids = {
            entry.unique_id for entry in self._async_current_entries()
        }
        self._discoveries = [
            discovery
            for discovery in discoveries
            if (
                _is_complete_discovery(discovery)
                and discovery.ssdp_usn not in current_unique_ids
            )
        ]

        # Ensure anything to add.
        if not self._discoveries:
            return self.async_abort(reason="no_devices_found")

        data_schema = vol.Schema(
            {
                vol.Required("unique_id"): vol.In(
                    {
                        discovery.ssdp_usn: _friendly_name_from_discovery(discovery)
                        for discovery in self._discoveries
                    }
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
        )

    async def async_step_import(self, import_info: Mapping | None) -> Mapping[str, Any]:
        """Import a new UPnP/IGD device as a config entry.

        This flow is triggered by `async_setup`. If no device has been
        configured before, find any device and create a config_entry for it.
        Otherwise, do nothing.
        """
        LOGGER.debug("async_step_import: import_info: %s", import_info)

        # Landed here via configuration.yaml entry.
        # Any device already added, then abort.
        if self._async_current_entries():
            LOGGER.debug("Already configured, aborting")
            return self.async_abort(reason="already_configured")

        # Discover devices.
        await _async_wait_for_discoveries(self.hass)
        discoveries = await _async_discover_igd_devices(self.hass)

        # Ensure anything to add. If not, silently abort.
        if not discoveries:
            LOGGER.info("No UPnP devices discovered, aborting")
            return self.async_abort(reason="no_devices_found")

        # Ensure complete discovery.
        discovery = discoveries[0]
        if not _is_complete_discovery(discovery):
            LOGGER.debug("Incomplete discovery, ignoring")
            return self.async_abort(reason="incomplete_discovery")

        # Ensure not already configuring/configured.
        unique_id = discovery.ssdp_usn
        await self.async_set_unique_id(unique_id)

        return await self._async_create_entry_from_discovery(discovery)

    async def async_step_ssdp(self, discovery_info: ssdp.SsdpServiceInfo) -> FlowResult:
        """Handle a discovered UPnP/IGD device.

        This flow is triggered by the SSDP component. It will check if the
        host is already configured and delegate to the import step if not.
        """
        LOGGER.debug("async_step_ssdp: discovery_info: %s", discovery_info)

        # Ensure complete discovery.
        if not _is_complete_discovery(discovery_info):
            LOGGER.debug("Incomplete discovery, ignoring")
            return self.async_abort(reason="incomplete_discovery")

        # Ensure not already configuring/configured.
        unique_id = discovery_info.ssdp_usn
        await self.async_set_unique_id(unique_id)
        hostname = discovery_info.ssdp_headers["_host"]
        self._abort_if_unique_id_configured(
            updates={CONFIG_ENTRY_HOSTNAME: hostname}, reload_on_update=False
        )

        # Handle devices changing their UDN, only allow a single host.
        existing_entries = self._async_current_entries()
        for config_entry in existing_entries:
            entry_hostname = config_entry.data.get(CONFIG_ENTRY_HOSTNAME)
            if entry_hostname == hostname:
                LOGGER.debug(
                    "Found existing config_entry with same hostname, discovery ignored"
                )
                return self.async_abort(reason="discovery_ignored")

        # Store discovery.
        self._discoveries = [discovery_info]

        # Ensure user recognizable.
        self.context["title_placeholders"] = {
            "name": _friendly_name_from_discovery(discovery_info),
        }

        return await self.async_step_ssdp_confirm()

    async def async_step_ssdp_confirm(
        self, user_input: Mapping | None = None
    ) -> FlowResult:
        """Confirm integration via SSDP."""
        LOGGER.debug("async_step_ssdp_confirm: user_input: %s", user_input)
        if user_input is None:
            return self.async_show_form(step_id="ssdp_confirm")

        assert self._discoveries
        discovery = self._discoveries[0]
        return await self._async_create_entry_from_discovery(discovery)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Define the config flow to handle options."""
        return UpnpOptionsFlowHandler(config_entry)

    async def _async_create_entry_from_discovery(
        self,
        discovery: SsdpServiceInfo,
    ) -> FlowResult:
        """Create an entry from discovery."""
        LOGGER.debug(
            "_async_create_entry_from_discovery: discovery: %s",
            discovery,
        )

        title = _friendly_name_from_discovery(discovery)
        data = {
            CONFIG_ENTRY_UDN: discovery.upnp[ssdp.ATTR_UPNP_UDN],
            CONFIG_ENTRY_ST: discovery.ssdp_st,
            CONFIG_ENTRY_HOSTNAME: discovery.ssdp_headers["_host"],
        }
        return self.async_create_entry(title=title, data=data)


class UpnpOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle a UPnP options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: Mapping = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]
            update_interval_sec = user_input.get(
                CONFIG_ENTRY_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
            )
            update_interval = timedelta(seconds=update_interval_sec)
            LOGGER.debug("Updating coordinator, update_interval: %s", update_interval)
            coordinator.update_interval = update_interval
            return self.async_create_entry(title="", data=user_input)

        scan_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=scan_interval,
                    ): vol.All(vol.Coerce(int), vol.Range(min=30)),
                }
            ),
        )
