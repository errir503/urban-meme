"""Config flow for the Open Thread Border Router integration."""
from __future__ import annotations

import logging

import python_otbr_api
import voluptuous as vol

from homeassistant.components.hassio import HassioServiceInfo
from homeassistant.components.thread import async_get_preferred_dataset
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_URL
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class OTBRConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Open Thread Border Router."""

    VERSION = 1

    async def _connect_and_create_dataset(self, url: str) -> None:
        """Connect to the OTBR and create a dataset if it doesn't have one."""
        api = python_otbr_api.OTBR(url, async_get_clientsession(self.hass), 10)
        if await api.get_active_dataset_tlvs() is None:
            if dataset := await async_get_preferred_dataset(self.hass):
                await api.set_active_dataset_tlvs(bytes.fromhex(dataset))
            else:
                await api.create_active_dataset(
                    python_otbr_api.OperationalDataSet(network_name="home-assistant")
                )
            await api.set_enabled(True)

    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Set up by user."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors = {}

        if user_input is not None:
            url = user_input[CONF_URL]
            try:
                await self._connect_and_create_dataset(url)
            except python_otbr_api.OTBRError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(DOMAIN)
                return self.async_create_entry(
                    title="Open Thread Border Router",
                    data=user_input,
                )

        data_schema = vol.Schema({CONF_URL: str})
        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def async_step_hassio(self, discovery_info: HassioServiceInfo) -> FlowResult:
        """Handle hassio discovery."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        config = discovery_info.config
        url = f"http://{config['host']}:{config['port']}"

        try:
            await self._connect_and_create_dataset(url)
        except python_otbr_api.OTBRError as exc:
            _LOGGER.warning("Failed to communicate with OTBR@%s: %s", url, exc)
            return self.async_abort(reason="unknown")

        await self.async_set_unique_id(DOMAIN)
        return self.async_create_entry(
            title="Open Thread Border Router",
            data={"url": url},
        )
