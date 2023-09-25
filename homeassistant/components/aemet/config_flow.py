"""Config flow for AEMET OpenData."""
from __future__ import annotations

from aemet_opendata.exceptions import AuthError
from aemet_opendata.interface import AEMET, ConnectionOptions
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client, config_validation as cv
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaFlowFormStep,
    SchemaOptionsFlowHandler,
)

from .const import CONF_STATION_UPDATES, DEFAULT_NAME, DOMAIN

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_STATION_UPDATES): bool,
    }
)
OPTIONS_FLOW = {
    "init": SchemaFlowFormStep(OPTIONS_SCHEMA),
}


class AemetConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for AEMET OpenData."""

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        errors = {}

        if user_input is not None:
            latitude = user_input[CONF_LATITUDE]
            longitude = user_input[CONF_LONGITUDE]

            await self.async_set_unique_id(f"{latitude}-{longitude}")
            self._abort_if_unique_id_configured()

            options = ConnectionOptions(user_input[CONF_API_KEY], False, True)
            aemet = AEMET(aiohttp_client.async_get_clientsession(self.hass), options)
            try:
                await aemet.select_coordinates(latitude, longitude)
            except AuthError:
                errors["base"] = "invalid_api_key"

            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=user_input
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Optional(
                    CONF_LATITUDE, default=self.hass.config.latitude
                ): cv.latitude,
                vol.Optional(
                    CONF_LONGITUDE, default=self.hass.config.longitude
                ): cv.longitude,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> SchemaOptionsFlowHandler:
        """Get the options flow for this handler."""
        return SchemaOptionsFlowHandler(config_entry, OPTIONS_FLOW)
