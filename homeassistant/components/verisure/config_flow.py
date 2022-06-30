"""Config flow for Verisure integration."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from verisure import (
    Error as VerisureError,
    LoginError as VerisureLoginError,
    ResponseError as VerisureResponseError,
    Session as Verisure,
)
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_GIID,
    CONF_LOCK_CODE_DIGITS,
    CONF_LOCK_DEFAULT_CODE,
    DEFAULT_LOCK_CODE_DIGITS,
    DOMAIN,
    LOGGER,
)


class VerisureConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Verisure."""

    VERSION = 1

    email: str
    entry: ConfigEntry
    installations: dict[str, str]
    password: str

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> VerisureOptionsFlowHandler:
        """Get the options flow for this handler."""
        return VerisureOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            verisure = Verisure(
                username=user_input[CONF_EMAIL], password=user_input[CONF_PASSWORD]
            )
            try:
                await self.hass.async_add_executor_job(verisure.login)
            except VerisureLoginError as ex:
                LOGGER.debug("Could not log in to Verisure, %s", ex)
                errors["base"] = "invalid_auth"
            except (VerisureError, VerisureResponseError) as ex:
                LOGGER.debug("Unexpected response from Verisure, %s", ex)
                errors["base"] = "unknown"
            else:
                self.email = user_input[CONF_EMAIL]
                self.password = user_input[CONF_PASSWORD]
                self.installations = {
                    inst["giid"]: f"{inst['alias']} ({inst['street']})"
                    for inst in verisure.installations
                }

                return await self.async_step_installation()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_installation(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select Verisure installation to add."""
        if len(self.installations) == 1:
            user_input = {CONF_GIID: list(self.installations)[0]}

        if user_input is None:
            return self.async_show_form(
                step_id="installation",
                data_schema=vol.Schema(
                    {vol.Required(CONF_GIID): vol.In(self.installations)}
                ),
            )

        await self.async_set_unique_id(user_input[CONF_GIID])
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=self.installations[user_input[CONF_GIID]],
            data={
                CONF_EMAIL: self.email,
                CONF_PASSWORD: self.password,
                CONF_GIID: user_input[CONF_GIID],
            },
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        """Handle initiation of re-authentication with Verisure."""
        self.entry = cast(
            ConfigEntry,
            self.hass.config_entries.async_get_entry(self.context["entry_id"]),
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle re-authentication with Verisure."""
        errors: dict[str, str] = {}

        if user_input is not None:
            verisure = Verisure(
                username=user_input[CONF_EMAIL], password=user_input[CONF_PASSWORD]
            )
            try:
                await self.hass.async_add_executor_job(verisure.login)
            except VerisureLoginError as ex:
                LOGGER.debug("Could not log in to Verisure, %s", ex)
                errors["base"] = "invalid_auth"
            except (VerisureError, VerisureResponseError) as ex:
                LOGGER.debug("Unexpected response from Verisure, %s", ex)
                errors["base"] = "unknown"
            else:
                data = self.entry.data.copy()
                self.hass.config_entries.async_update_entry(
                    self.entry,
                    data={
                        **data,
                        CONF_EMAIL: user_input[CONF_EMAIL],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(self.entry.entry_id)
                )
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL, default=self.entry.data[CONF_EMAIL]): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )


class VerisureOptionsFlowHandler(OptionsFlow):
    """Handle Verisure options."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize Verisure options flow."""
        self.entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage Verisure options."""
        errors = {}

        if user_input is not None:
            if len(user_input[CONF_LOCK_DEFAULT_CODE]) not in [
                0,
                user_input[CONF_LOCK_CODE_DIGITS],
            ]:
                errors["base"] = "code_format_mismatch"
            else:
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_LOCK_CODE_DIGITS,
                        default=self.entry.options.get(
                            CONF_LOCK_CODE_DIGITS, DEFAULT_LOCK_CODE_DIGITS
                        ),
                    ): int,
                    vol.Optional(
                        CONF_LOCK_DEFAULT_CODE,
                        default=self.entry.options.get(CONF_LOCK_DEFAULT_CODE),
                    ): str,
                }
            ),
            errors=errors,
        )
