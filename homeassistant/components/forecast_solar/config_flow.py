"""Config flow for Forecast.Solar integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_AZIMUTH,
    CONF_DAMPING,
    CONF_DECLINATION,
    CONF_INVERTER_SIZE,
    CONF_MODULES_POWER,
    DOMAIN,
)


class ForecastSolarFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Forecast.Solar."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> ForecastSolarOptionFlowHandler:
        """Get the options flow for this handler."""
        return ForecastSolarOptionFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initiated by the user."""
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={
                    CONF_LATITUDE: user_input[CONF_LATITUDE],
                    CONF_LONGITUDE: user_input[CONF_LONGITUDE],
                },
                options={
                    CONF_AZIMUTH: user_input[CONF_AZIMUTH],
                    CONF_DECLINATION: user_input[CONF_DECLINATION],
                    CONF_MODULES_POWER: user_input[CONF_MODULES_POWER],
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NAME, default=self.hass.config.location_name
                    ): str,
                    vol.Required(
                        CONF_LATITUDE, default=self.hass.config.latitude
                    ): cv.latitude,
                    vol.Required(
                        CONF_LONGITUDE, default=self.hass.config.longitude
                    ): cv.longitude,
                    vol.Required(CONF_DECLINATION, default=25): vol.All(
                        vol.Coerce(int), vol.Range(min=0, max=90)
                    ),
                    vol.Required(CONF_AZIMUTH, default=180): vol.All(
                        vol.Coerce(int), vol.Range(min=0, max=360)
                    ),
                    vol.Required(CONF_MODULES_POWER): vol.Coerce(int),
                }
            ),
        )


class ForecastSolarOptionFlowHandler(OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_API_KEY,
                        description={
                            "suggested_value": self.config_entry.options.get(
                                CONF_API_KEY, ""
                            )
                        },
                    ): str,
                    vol.Required(
                        CONF_DECLINATION,
                        default=self.config_entry.options[CONF_DECLINATION],
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=90)),
                    vol.Required(
                        CONF_AZIMUTH,
                        default=self.config_entry.options.get(CONF_AZIMUTH),
                    ): vol.All(vol.Coerce(int), vol.Range(min=-0, max=360)),
                    vol.Required(
                        CONF_MODULES_POWER,
                        default=self.config_entry.options[CONF_MODULES_POWER],
                    ): vol.Coerce(int),
                    vol.Optional(
                        CONF_DAMPING,
                        default=self.config_entry.options.get(CONF_DAMPING, 0.0),
                    ): vol.Coerce(float),
                    vol.Optional(
                        CONF_INVERTER_SIZE,
                        description={
                            "suggested_value": self.config_entry.options.get(
                                CONF_INVERTER_SIZE
                            )
                        },
                    ): vol.Coerce(int),
                }
            ),
        )
