"""Config flow for Airzone."""
from __future__ import annotations

from typing import Any

from aioairzone.common import ConnectionOptions
from aioairzone.exceptions import InvalidHost
from aioairzone.localapi_device import AirzoneLocalApi
from aiohttp.client_exceptions import ClientConnectorError
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client

from .const import DEFAULT_LOCAL_API_PORT, DOMAIN


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for an Airzone device."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            self._async_abort_entries_match(
                {
                    CONF_HOST: user_input[CONF_HOST],
                    CONF_PORT: user_input[CONF_PORT],
                }
            )

            airzone = AirzoneLocalApi(
                aiohttp_client.async_get_clientsession(self.hass),
                ConnectionOptions(
                    user_input[CONF_HOST],
                    user_input[CONF_PORT],
                ),
            )

            try:
                await airzone.validate_airzone()
            except (ClientConnectorError, InvalidHost):
                errors["base"] = "cannot_connect"
            else:
                title = f"Airzone {user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_PORT, default=DEFAULT_LOCAL_API_PORT): int,
                }
            ),
            errors=errors,
        )
