"""Config flow for baf."""
from __future__ import annotations

import asyncio
from asyncio import timeout
import logging
from typing import Any

from aiobafi6 import Device, Service
from aiobafi6.discovery import PORT
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import zeroconf
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, RUN_TIMEOUT
from .models import BAFDiscovery

_LOGGER = logging.getLogger(__name__)


async def async_try_connect(ip_address: str) -> Device:
    """Validate we can connect to a device."""
    device = Device(Service(ip_addresses=[ip_address], port=PORT))
    run_future = device.async_run()
    try:
        async with timeout(RUN_TIMEOUT):
            await device.async_wait_available()
    except asyncio.TimeoutError as ex:
        raise CannotConnect from ex
    finally:
        run_future.cancel()
    return device


class BAFFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle BAF discovery config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the BAF config flow."""
        self.discovery: BAFDiscovery | None = None

    async def async_step_zeroconf(
        self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> FlowResult:
        """Handle zeroconf discovery."""
        if discovery_info.ip_address.version == 6:
            return self.async_abort(reason="ipv6_not_supported")
        properties = discovery_info.properties
        ip_address = discovery_info.host
        uuid = properties["uuid"]
        model = properties["model"]
        name = properties["name"]
        await self.async_set_unique_id(uuid)
        self._abort_if_unique_id_configured(updates={CONF_IP_ADDRESS: ip_address})
        self.discovery = BAFDiscovery(ip_address, name, uuid, model)
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery."""
        assert self.discovery is not None
        discovery = self.discovery
        if user_input is not None:
            return self.async_create_entry(
                title=discovery.name,
                data={CONF_IP_ADDRESS: discovery.ip_address},
            )
        placeholders = {
            "name": discovery.name,
            "model": discovery.model,
            "ip_address": discovery.ip_address,
        }
        self.context["title_placeholders"] = placeholders
        self._set_confirm_only()
        return self.async_show_form(
            step_id="discovery_confirm", description_placeholders=placeholders
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}
        ip_address = (user_input or {}).get(CONF_IP_ADDRESS, "")
        if user_input is not None:
            try:
                device = await async_try_connect(ip_address)
            except CannotConnect:
                errors[CONF_IP_ADDRESS] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception(
                    "Unknown exception during connection test to %s", ip_address
                )
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(
                    device.dns_sd_uuid, raise_on_progress=False
                )
                self._abort_if_unique_id_configured(
                    updates={CONF_IP_ADDRESS: ip_address}
                )
                return self.async_create_entry(
                    title=device.name,
                    data={CONF_IP_ADDRESS: ip_address},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_IP_ADDRESS, default=ip_address): str}
            ),
            errors=errors,
        )


class CannotConnect(Exception):
    """Exception to raise when we cannot connect."""
