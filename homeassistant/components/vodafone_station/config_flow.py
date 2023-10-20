"""Config flow for Vodafone Station integration."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiovodafone import VodafoneStationSercommApi, exceptions as aiovodafone_exceptions
import voluptuous as vol

from homeassistant import core
from homeassistant.config_entries import ConfigEntry, ConfigFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult

from .const import _LOGGER, DEFAULT_HOST, DEFAULT_USERNAME, DOMAIN


def user_form_schema(user_input: dict[str, Any] | None) -> vol.Schema:
    """Return user form schema."""
    user_input = user_input or {}
    return vol.Schema(
        {
            vol.Optional(CONF_HOST, default=DEFAULT_HOST): str,
            vol.Optional(CONF_USERNAME, default=DEFAULT_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
        }
    )


STEP_REAUTH_DATA_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): str})


async def validate_input(
    hass: core.HomeAssistant, data: dict[str, Any]
) -> dict[str, str]:
    """Validate the user input allows us to connect."""

    api = VodafoneStationSercommApi(
        data[CONF_HOST], data[CONF_USERNAME], data[CONF_PASSWORD]
    )

    try:
        await api.login()
    finally:
        await api.logout()
        await api.close()

    return {"title": data[CONF_HOST]}


class VodafoneStationConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vodafone Station."""

    VERSION = 1
    entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=user_form_schema(user_input)
            )

        # Use host because no serial number or mac is available to use for a unique id
        self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})

        errors = {}

        try:
            info = await validate_input(self.hass, user_input)
        except aiovodafone_exceptions.AlreadyLogged:
            errors["base"] = "already_logged"
        except aiovodafone_exceptions.CannotConnect:
            errors["base"] = "cannot_connect"
        except aiovodafone_exceptions.CannotAuthenticate:
            errors["base"] = "invalid_auth"
        except aiovodafone_exceptions.ModelNotSupported:
            errors["base"] = "model_not_supported"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=user_form_schema(user_input), errors=errors
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        """Handle reauth flow."""
        self.entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert self.entry
        self.context["title_placeholders"] = {"host": self.entry.data[CONF_HOST]}
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reauth confirm."""
        assert self.entry
        errors = {}

        if user_input is not None:
            try:
                await validate_input(self.hass, {**self.entry.data, **user_input})
            except aiovodafone_exceptions.AlreadyLogged:
                errors["base"] = "already_logged"
            except aiovodafone_exceptions.CannotConnect:
                errors["base"] = "cannot_connect"
            except aiovodafone_exceptions.CannotAuthenticate:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    self.entry,
                    data={
                        **self.entry.data,
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(self.entry.entry_id)
                )
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            description_placeholders={CONF_HOST: self.entry.data[CONF_HOST]},
            data_schema=STEP_REAUTH_DATA_SCHEMA,
            errors=errors,
        )
