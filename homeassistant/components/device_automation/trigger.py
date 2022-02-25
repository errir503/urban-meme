"""Offer device oriented automation."""
from typing import Protocol, cast

import voluptuous as vol

from homeassistant.components.automation import (
    AutomationActionType,
    AutomationTriggerInfo,
)
from homeassistant.const import CONF_DOMAIN
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.typing import ConfigType

from . import (
    DEVICE_TRIGGER_BASE_SCHEMA,
    DeviceAutomationType,
    async_get_device_automation_platform,
)
from .exceptions import InvalidDeviceAutomationConfig

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend({}, extra=vol.ALLOW_EXTRA)


class DeviceAutomationTriggerProtocol(Protocol):
    """Define the format of device_trigger modules.

    Each module must define either TRIGGER_SCHEMA or async_validate_trigger_config.
    """

    TRIGGER_SCHEMA: vol.Schema

    async def async_validate_trigger_config(
        self, hass: HomeAssistant, config: ConfigType
    ) -> ConfigType:
        """Validate config."""
        raise NotImplementedError

    async def async_attach_trigger(
        self,
        hass: HomeAssistant,
        config: ConfigType,
        action: AutomationActionType,
        automation_info: AutomationTriggerInfo,
    ) -> CALLBACK_TYPE:
        """Attach a trigger."""
        raise NotImplementedError


async def async_validate_trigger_config(
    hass: HomeAssistant, config: ConfigType
) -> ConfigType:
    """Validate config."""
    try:
        platform = await async_get_device_automation_platform(
            hass, config[CONF_DOMAIN], DeviceAutomationType.TRIGGER
        )
        if not hasattr(platform, "async_validate_trigger_config"):
            return cast(ConfigType, platform.TRIGGER_SCHEMA(config))
        return await platform.async_validate_trigger_config(hass, config)
    except InvalidDeviceAutomationConfig as err:
        raise vol.Invalid(str(err) or "Invalid trigger configuration") from err


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: AutomationActionType,
    automation_info: AutomationTriggerInfo,
) -> CALLBACK_TYPE:
    """Listen for trigger."""
    platform = await async_get_device_automation_platform(
        hass, config[CONF_DOMAIN], DeviceAutomationType.TRIGGER
    )
    return await platform.async_attach_trigger(hass, config, action, automation_info)
