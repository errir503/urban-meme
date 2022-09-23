"""Config validation helper for the automation integration."""
from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

import voluptuous as vol

from homeassistant.components import blueprint
from homeassistant.components.device_automation.exceptions import (
    InvalidDeviceAutomationConfig,
)
from homeassistant.components.trace import TRACE_CONFIG_SCHEMA
from homeassistant.config import async_log_exception, config_without_domain
from homeassistant.const import (
    CONF_ALIAS,
    CONF_CONDITION,
    CONF_DESCRIPTION,
    CONF_ID,
    CONF_VARIABLES,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_per_platform, config_validation as cv, script
from homeassistant.helpers.condition import async_validate_conditions_config
from homeassistant.helpers.trigger import async_validate_trigger_config
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import IntegrationNotFound

from .const import (
    CONF_ACTION,
    CONF_HIDE_ENTITY,
    CONF_INITIAL_STATE,
    CONF_TRACE,
    CONF_TRIGGER,
    CONF_TRIGGER_VARIABLES,
    DOMAIN,
)
from .helpers import async_get_blueprints

PACKAGE_MERGE_HINT = "list"

_CONDITION_SCHEMA = vol.All(cv.ensure_list, [cv.CONDITION_SCHEMA])

PLATFORM_SCHEMA = vol.All(
    cv.deprecated(CONF_HIDE_ENTITY),
    script.make_script_schema(
        {
            # str on purpose
            CONF_ID: str,
            CONF_ALIAS: cv.string,
            vol.Optional(CONF_DESCRIPTION): cv.string,
            vol.Optional(CONF_TRACE, default={}): TRACE_CONFIG_SCHEMA,
            vol.Optional(CONF_INITIAL_STATE): cv.boolean,
            vol.Optional(CONF_HIDE_ENTITY): cv.boolean,
            vol.Required(CONF_TRIGGER): cv.TRIGGER_SCHEMA,
            vol.Optional(CONF_CONDITION): _CONDITION_SCHEMA,
            vol.Optional(CONF_VARIABLES): cv.SCRIPT_VARIABLES_SCHEMA,
            vol.Optional(CONF_TRIGGER_VARIABLES): cv.SCRIPT_VARIABLES_SCHEMA,
            vol.Required(CONF_ACTION): cv.SCRIPT_SCHEMA,
        },
        script.SCRIPT_MODE_SINGLE,
    ),
)


async def async_validate_config_item(
    hass: HomeAssistant,
    config: ConfigType,
    full_config: ConfigType | None = None,
) -> blueprint.BlueprintInputs | dict[str, Any]:
    """Validate config item."""
    if blueprint.is_blueprint_instance_config(config):
        blueprints = async_get_blueprints(hass)
        return await blueprints.async_inputs_from_config(config)

    config = PLATFORM_SCHEMA(config)

    config[CONF_TRIGGER] = await async_validate_trigger_config(
        hass, config[CONF_TRIGGER]
    )

    if CONF_CONDITION in config:
        config[CONF_CONDITION] = await async_validate_conditions_config(
            hass, config[CONF_CONDITION]
        )

    config[CONF_ACTION] = await script.async_validate_actions_config(
        hass, config[CONF_ACTION]
    )

    return config


class AutomationConfig(dict):
    """Dummy class to allow adding attributes."""

    raw_config: dict[str, Any] | None = None


async def _try_async_validate_config_item(
    hass: HomeAssistant,
    config: dict[str, Any],
    full_config: dict[str, Any] | None = None,
) -> AutomationConfig | blueprint.BlueprintInputs | None:
    """Validate config item."""
    raw_config = None
    with suppress(ValueError):
        raw_config = dict(config)

    try:
        validated_config = await async_validate_config_item(hass, config, full_config)
    except (
        vol.Invalid,
        HomeAssistantError,
        IntegrationNotFound,
        InvalidDeviceAutomationConfig,
    ) as ex:
        async_log_exception(ex, DOMAIN, full_config or config, hass)
        return None

    if isinstance(validated_config, blueprint.BlueprintInputs):
        return validated_config

    automation_config = AutomationConfig(validated_config)
    automation_config.raw_config = raw_config
    return automation_config


async def async_validate_config(hass: HomeAssistant, config: ConfigType) -> ConfigType:
    """Validate config."""
    automations = list(
        filter(
            lambda x: x is not None,
            await asyncio.gather(
                *(
                    _try_async_validate_config_item(hass, p_config, config)
                    for _, p_config in config_per_platform(config, DOMAIN)
                )
            ),
        )
    )

    # Create a copy of the configuration with all config for current
    # component removed and add validated config back in.
    config = config_without_domain(config, DOMAIN)
    config[DOMAIN] = automations

    return config
