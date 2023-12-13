"""Config Flow for OSO Energy."""
from collections.abc import Mapping
import logging
from typing import Any

from apyosoenergyapi import OSOEnergy
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
_SCHEMA_STEP_USER = vol.Schema({vol.Required(CONF_API_KEY): str})


class OSOEnergyFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a OSO Energy config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self) -> None:
        """Initialize."""
        self.entry: ConfigEntry | None = None

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle a flow initialized by the user."""
        errors = {}

        if user_input is not None:
            # Verify Subscription key
            if user_email := await self.get_user_email(user_input[CONF_API_KEY]):
                await self.async_set_unique_id(user_email)

                if (
                    self.context["source"] == config_entries.SOURCE_REAUTH
                    and self.entry
                ):
                    self.hass.config_entries.async_update_entry(
                        self.entry, title=user_email, data=user_input
                    )
                    await self.hass.config_entries.async_reload(self.entry.entry_id)
                    return self.async_abort(reason="reauth_successful")

                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=user_email, data=user_input)

            errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="user",
            data_schema=_SCHEMA_STEP_USER,
            errors=errors,
        )

    async def get_user_email(self, subscription_key: str) -> str | None:
        """Return the user email for the provided subscription key."""
        try:
            websession = aiohttp_client.async_get_clientsession(self.hass)
            client = OSOEnergy(subscription_key, websession)
            return await client.get_user_email()
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unknown error occurred")
        return None

    async def async_step_reauth(self, user_input: Mapping[str, Any]) -> FlowResult:
        """Re Authenticate a user."""
        self.entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        data = {CONF_API_KEY: user_input[CONF_API_KEY]}
        return await self.async_step_user(data)
