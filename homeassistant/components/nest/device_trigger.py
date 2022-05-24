"""Provides device automations for Nest."""
from __future__ import annotations

from google_nest_sdm.device_manager import DeviceManager
import voluptuous as vol

from homeassistant.components.automation import (
    AutomationActionType,
    AutomationTriggerInfo,
)
from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.device_automation.exceptions import (
    InvalidDeviceAutomationConfig,
)
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import DATA_DEVICE_MANAGER, DOMAIN
from .events import DEVICE_TRAIT_TRIGGER_MAP, NEST_EVENT

DEVICE = "device"

TRIGGER_TYPES = set(DEVICE_TRAIT_TRIGGER_MAP.values())

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
    }
)


@callback
def async_get_nest_device_id(hass: HomeAssistant, device_id: str) -> str | None:
    """Get the nest API device_id from the HomeAssistant device_id."""
    device_registry = dr.async_get(hass)
    if device := device_registry.async_get(device_id):
        for (domain, unique_id) in device.identifiers:
            if domain == DOMAIN:
                return unique_id
    return None


@callback
def async_get_device_trigger_types(
    hass: HomeAssistant, nest_device_id: str
) -> list[str]:
    """List event triggers supported for a Nest device."""
    device_manager: DeviceManager = hass.data[DOMAIN][DATA_DEVICE_MANAGER]
    if not (nest_device := device_manager.devices.get(nest_device_id)):
        raise InvalidDeviceAutomationConfig(f"Nest device not found {nest_device_id}")

    # Determine the set of event types based on the supported device traits
    trigger_types = [
        trigger_type
        for trait in nest_device.traits
        if (trigger_type := DEVICE_TRAIT_TRIGGER_MAP.get(trait))
    ]
    return trigger_types


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """List device triggers for a Nest device."""
    nest_device_id = async_get_nest_device_id(hass, device_id)
    if not nest_device_id:
        raise InvalidDeviceAutomationConfig(f"Device not found {device_id}")
    trigger_types = async_get_device_trigger_types(hass, nest_device_id)
    return [
        {
            CONF_PLATFORM: DEVICE,
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: trigger_type,
        }
        for trigger_type in trigger_types
    ]


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: AutomationActionType,
    automation_info: AutomationTriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a trigger."""
    event_config = event_trigger.TRIGGER_SCHEMA(
        {
            event_trigger.CONF_PLATFORM: "event",
            event_trigger.CONF_EVENT_TYPE: NEST_EVENT,
            event_trigger.CONF_EVENT_DATA: {
                CONF_DEVICE_ID: config[CONF_DEVICE_ID],
                CONF_TYPE: config[CONF_TYPE],
            },
        }
    )
    return await event_trigger.async_attach_trigger(
        hass, event_config, action, automation_info, platform_type="device"
    )
