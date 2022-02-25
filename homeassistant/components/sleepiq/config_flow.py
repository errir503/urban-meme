"""Config flow to configure SleepIQ component."""
from __future__ import annotations

from typing import Any

from asyncsleepiq import AsyncSleepIQ, SleepIQLoginException, SleepIQTimeoutException
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN


class SleepIQFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a SleepIQ config flow."""

    VERSION = 1

    async def async_step_import(self, import_config: dict[str, Any]) -> FlowResult:
        """Import a SleepIQ account as a config entry.

        This flow is triggered by 'async_setup' for configured accounts.
        """
        await self.async_set_unique_id(import_config[CONF_USERNAME].lower())
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=import_config[CONF_USERNAME], data=import_config
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initialized by the user."""
        errors = {}

        if user_input is not None:
            # Don't allow multiple instances with the same username
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()

            try:
                await try_connection(self.hass, user_input)
            except SleepIQLoginException:
                errors["base"] = "invalid_auth"
            except SleepIQTimeoutException:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME], data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=user_input.get(CONF_USERNAME)
                        if user_input is not None
                        else "",
                    ): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
            last_step=True,
        )


async def try_connection(hass: HomeAssistant, user_input: dict[str, Any]) -> None:
    """Test if the given credentials can successfully login to SleepIQ."""

    client_session = async_get_clientsession(hass)

    gateway = AsyncSleepIQ(client_session=client_session)
    await gateway.login(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
