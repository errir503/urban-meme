"""Provides device actions for ZHA devices."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_TYPE
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType, TemplateVarsType

from . import DOMAIN
from .api import SERVICE_WARNING_DEVICE_SQUAWK, SERVICE_WARNING_DEVICE_WARN
from .core.const import CHANNEL_IAS_WD
from .core.helpers import async_get_zha_device

# mypy: disallow-any-generics

ACTION_SQUAWK = "squawk"
ACTION_WARN = "warn"
ATTR_DATA = "data"
ATTR_IEEE = "ieee"
CONF_ZHA_ACTION_TYPE = "zha_action_type"
ZHA_ACTION_TYPE_SERVICE_CALL = "service_call"

ACTION_SCHEMA = cv.DEVICE_ACTION_BASE_SCHEMA.extend(
    {vol.Required(CONF_DOMAIN): DOMAIN, vol.Required(CONF_TYPE): str}
)

DEVICE_ACTIONS = {
    CHANNEL_IAS_WD: [
        {CONF_TYPE: ACTION_SQUAWK, CONF_DOMAIN: DOMAIN},
        {CONF_TYPE: ACTION_WARN, CONF_DOMAIN: DOMAIN},
    ]
}

DEVICE_ACTION_TYPES = {
    ACTION_SQUAWK: ZHA_ACTION_TYPE_SERVICE_CALL,
    ACTION_WARN: ZHA_ACTION_TYPE_SERVICE_CALL,
}

SERVICE_NAMES = {
    ACTION_SQUAWK: SERVICE_WARNING_DEVICE_SQUAWK,
    ACTION_WARN: SERVICE_WARNING_DEVICE_WARN,
}


async def async_call_action_from_config(
    hass: HomeAssistant,
    config: ConfigType,
    variables: TemplateVarsType,
    context: Context | None,
) -> None:
    """Perform an action based on configuration."""
    await ZHA_ACTION_TYPES[DEVICE_ACTION_TYPES[config[CONF_TYPE]]](
        hass, config, variables, context
    )


async def async_get_actions(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """List device actions."""
    try:
        zha_device = async_get_zha_device(hass, device_id)
    except (KeyError, AttributeError):
        return []
    cluster_channels = [
        ch.name
        for pool in zha_device.channels.pools
        for ch in pool.claimed_channels.values()
    ]
    actions = [
        action
        for channel, channel_actions in DEVICE_ACTIONS.items()
        for action in channel_actions
        if channel in cluster_channels
    ]
    for action in actions:
        action[CONF_DEVICE_ID] = device_id
    return actions


async def _execute_service_based_action(
    hass: HomeAssistant,
    config: dict[str, Any],
    variables: TemplateVarsType,
    context: Context | None,
) -> None:
    action_type = config[CONF_TYPE]
    service_name = SERVICE_NAMES[action_type]
    try:
        zha_device = async_get_zha_device(hass, config[CONF_DEVICE_ID])
    except (KeyError, AttributeError):
        return

    service_data = {ATTR_IEEE: str(zha_device.ieee)}

    await hass.services.async_call(
        DOMAIN, service_name, service_data, blocking=True, context=context
    )


ZHA_ACTION_TYPES = {ZHA_ACTION_TYPE_SERVICE_CALL: _execute_service_based_action}
