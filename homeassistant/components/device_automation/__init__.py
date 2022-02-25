"""Helpers for device automations."""
from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from enum import Enum
from functools import wraps
import logging
from types import ModuleType
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, Union, overload

import voluptuous as vol
import voluptuous_serialize

from homeassistant.components import websocket_api
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.frame import report
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import IntegrationNotFound, bind_hass
from homeassistant.requirements import async_get_integration_with_requirements

from .exceptions import DeviceNotFound, InvalidDeviceAutomationConfig

if TYPE_CHECKING:
    from .action import DeviceAutomationActionProtocol
    from .condition import DeviceAutomationConditionProtocol
    from .trigger import DeviceAutomationTriggerProtocol

    DeviceAutomationPlatformType = Union[
        ModuleType,
        DeviceAutomationTriggerProtocol,
        DeviceAutomationConditionProtocol,
        DeviceAutomationActionProtocol,
    ]

# mypy: allow-untyped-calls, allow-untyped-defs

DOMAIN = "device_automation"

DEVICE_TRIGGER_BASE_SCHEMA = cv.TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_PLATFORM): "device",
        vol.Required(CONF_DOMAIN): str,
        vol.Required(CONF_DEVICE_ID): str,
    }
)


class DeviceAutomationDetails(NamedTuple):
    """Details for device automation."""

    section: str
    get_automations_func: str
    get_capabilities_func: str


class DeviceAutomationType(Enum):
    """Device automation type."""

    TRIGGER = DeviceAutomationDetails(
        "device_trigger",
        "async_get_triggers",
        "async_get_trigger_capabilities",
    )
    CONDITION = DeviceAutomationDetails(
        "device_condition",
        "async_get_conditions",
        "async_get_condition_capabilities",
    )
    ACTION = DeviceAutomationDetails(
        "device_action",
        "async_get_actions",
        "async_get_action_capabilities",
    )


# TYPES is deprecated as of Home Assistant 2022.2, use DeviceAutomationType instead
TYPES = {
    "trigger": DeviceAutomationType.TRIGGER.value,
    "condition": DeviceAutomationType.CONDITION.value,
    "action": DeviceAutomationType.ACTION.value,
}


@bind_hass
async def async_get_device_automations(
    hass: HomeAssistant,
    automation_type: DeviceAutomationType | str,
    device_ids: Iterable[str] | None = None,
) -> Mapping[str, Any]:
    """Return all the device automations for a type optionally limited to specific device ids."""
    if isinstance(automation_type, str):
        report(
            "uses str for async_get_device_automations automation_type. This is "
            "deprecated and will stop working in Home Assistant 2022.4, it should be "
            "updated to use DeviceAutomationType instead",
            error_if_core=False,
        )
        automation_type = DeviceAutomationType[automation_type.upper()]
    return await _async_get_device_automations(hass, automation_type, device_ids)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up device automation."""
    websocket_api.async_register_command(hass, websocket_device_automation_list_actions)
    websocket_api.async_register_command(
        hass, websocket_device_automation_list_conditions
    )
    websocket_api.async_register_command(
        hass, websocket_device_automation_list_triggers
    )
    websocket_api.async_register_command(
        hass, websocket_device_automation_get_action_capabilities
    )
    websocket_api.async_register_command(
        hass, websocket_device_automation_get_condition_capabilities
    )
    websocket_api.async_register_command(
        hass, websocket_device_automation_get_trigger_capabilities
    )
    return True


@overload
async def async_get_device_automation_platform(  # noqa: D103
    hass: HomeAssistant,
    domain: str,
    automation_type: Literal[DeviceAutomationType.TRIGGER],
) -> DeviceAutomationTriggerProtocol:
    ...


@overload
async def async_get_device_automation_platform(  # noqa: D103
    hass: HomeAssistant,
    domain: str,
    automation_type: Literal[DeviceAutomationType.CONDITION],
) -> DeviceAutomationConditionProtocol:
    ...


@overload
async def async_get_device_automation_platform(  # noqa: D103
    hass: HomeAssistant,
    domain: str,
    automation_type: Literal[DeviceAutomationType.ACTION],
) -> DeviceAutomationActionProtocol:
    ...


@overload
async def async_get_device_automation_platform(  # noqa: D103
    hass: HomeAssistant, domain: str, automation_type: DeviceAutomationType | str
) -> "DeviceAutomationPlatformType":
    ...


async def async_get_device_automation_platform(
    hass: HomeAssistant, domain: str, automation_type: DeviceAutomationType | str
) -> "DeviceAutomationPlatformType":
    """Load device automation platform for integration.

    Throws InvalidDeviceAutomationConfig if the integration is not found or does not support device automation.
    """
    if isinstance(automation_type, str):
        report(
            "uses str for async_get_device_automation_platform automation_type. This "
            "is deprecated and will stop working in Home Assistant 2022.4, it should "
            "be updated to use DeviceAutomationType instead",
            error_if_core=False,
        )
        automation_type = DeviceAutomationType[automation_type.upper()]
    platform_name = automation_type.value.section
    try:
        integration = await async_get_integration_with_requirements(hass, domain)
        platform = integration.get_platform(platform_name)
    except IntegrationNotFound as err:
        raise InvalidDeviceAutomationConfig(
            f"Integration '{domain}' not found"
        ) from err
    except ImportError as err:
        raise InvalidDeviceAutomationConfig(
            f"Integration '{domain}' does not support device automation "
            f"{automation_type.name.lower()}s"
        ) from err

    return platform


async def _async_get_device_automations_from_domain(
    hass, domain, automation_type, device_ids, return_exceptions
):
    """List device automations."""
    try:
        platform = await async_get_device_automation_platform(
            hass, domain, automation_type
        )
    except InvalidDeviceAutomationConfig:
        return {}

    function_name = automation_type.value.get_automations_func

    return await asyncio.gather(
        *(
            getattr(platform, function_name)(hass, device_id)
            for device_id in device_ids
        ),
        return_exceptions=return_exceptions,
    )


async def _async_get_device_automations(
    hass: HomeAssistant,
    automation_type: DeviceAutomationType,
    device_ids: Iterable[str] | None,
) -> Mapping[str, list[dict[str, Any]]]:
    """List device automations."""
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    domain_devices: dict[str, set[str]] = {}
    device_entities_domains: dict[str, set[str]] = {}
    match_device_ids = set(device_ids or device_registry.devices)
    combined_results: dict[str, list[dict[str, Any]]] = {}

    for entry in entity_registry.entities.values():
        if not entry.disabled_by and entry.device_id in match_device_ids:
            device_entities_domains.setdefault(entry.device_id, set()).add(entry.domain)

    for device_id in match_device_ids:
        combined_results[device_id] = []
        if (device := device_registry.async_get(device_id)) is None:
            raise DeviceNotFound
        for entry_id in device.config_entries:
            if config_entry := hass.config_entries.async_get_entry(entry_id):
                domain_devices.setdefault(config_entry.domain, set()).add(device_id)
        for domain in device_entities_domains.get(device_id, []):
            domain_devices.setdefault(domain, set()).add(device_id)

    # If specific device ids were requested, we allow
    # InvalidDeviceAutomationConfig to be thrown, otherwise we skip
    # devices that do not have valid triggers
    return_exceptions = not bool(device_ids)

    for domain_results in await asyncio.gather(
        *(
            _async_get_device_automations_from_domain(
                hass, domain, automation_type, domain_device_ids, return_exceptions
            )
            for domain, domain_device_ids in domain_devices.items()
        )
    ):
        for device_results in domain_results:
            if device_results is None or isinstance(
                device_results, InvalidDeviceAutomationConfig
            ):
                continue
            if isinstance(device_results, Exception):
                logging.getLogger(__name__).error(
                    "Unexpected error fetching device %ss",
                    automation_type.name.lower(),
                    exc_info=device_results,
                )
                continue
            for automation in device_results:
                combined_results[automation["device_id"]].append(automation)

    return combined_results


async def _async_get_device_automation_capabilities(
    hass: HomeAssistant,
    automation_type: DeviceAutomationType,
    automation: Mapping[str, Any],
) -> dict[str, Any]:
    """List device automations."""
    try:
        platform = await async_get_device_automation_platform(
            hass, automation[CONF_DOMAIN], automation_type
        )
    except InvalidDeviceAutomationConfig:
        return {}

    function_name = automation_type.value.get_capabilities_func

    if not hasattr(platform, function_name):
        # The device automation has no capabilities
        return {}

    try:
        capabilities = await getattr(platform, function_name)(hass, automation)
    except InvalidDeviceAutomationConfig:
        return {}

    capabilities = capabilities.copy()

    if (extra_fields := capabilities.get("extra_fields")) is None:
        capabilities["extra_fields"] = []
    else:
        capabilities["extra_fields"] = voluptuous_serialize.convert(
            extra_fields, custom_serializer=cv.custom_serializer
        )

    return capabilities  # type: ignore[no-any-return]


def handle_device_errors(func):
    """Handle device automation errors."""

    @wraps(func)
    async def with_error_handling(hass, connection, msg):
        try:
            await func(hass, connection, msg)
        except DeviceNotFound:
            connection.send_error(
                msg["id"], websocket_api.const.ERR_NOT_FOUND, "Device not found"
            )

    return with_error_handling


@websocket_api.websocket_command(
    {
        vol.Required("type"): "device_automation/action/list",
        vol.Required("device_id"): str,
    }
)
@websocket_api.async_response
@handle_device_errors
async def websocket_device_automation_list_actions(hass, connection, msg):
    """Handle request for device actions."""
    device_id = msg["device_id"]
    actions = (
        await _async_get_device_automations(
            hass, DeviceAutomationType.ACTION, [device_id]
        )
    ).get(device_id)
    connection.send_result(msg["id"], actions)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "device_automation/condition/list",
        vol.Required("device_id"): str,
    }
)
@websocket_api.async_response
@handle_device_errors
async def websocket_device_automation_list_conditions(hass, connection, msg):
    """Handle request for device conditions."""
    device_id = msg["device_id"]
    conditions = (
        await _async_get_device_automations(
            hass, DeviceAutomationType.CONDITION, [device_id]
        )
    ).get(device_id)
    connection.send_result(msg["id"], conditions)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "device_automation/trigger/list",
        vol.Required("device_id"): str,
    }
)
@websocket_api.async_response
@handle_device_errors
async def websocket_device_automation_list_triggers(hass, connection, msg):
    """Handle request for device triggers."""
    device_id = msg["device_id"]
    triggers = (
        await _async_get_device_automations(
            hass, DeviceAutomationType.TRIGGER, [device_id]
        )
    ).get(device_id)
    connection.send_result(msg["id"], triggers)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "device_automation/action/capabilities",
        vol.Required("action"): dict,
    }
)
@websocket_api.async_response
@handle_device_errors
async def websocket_device_automation_get_action_capabilities(hass, connection, msg):
    """Handle request for device action capabilities."""
    action = msg["action"]
    capabilities = await _async_get_device_automation_capabilities(
        hass, DeviceAutomationType.ACTION, action
    )
    connection.send_result(msg["id"], capabilities)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "device_automation/condition/capabilities",
        vol.Required("condition"): cv.DEVICE_CONDITION_BASE_SCHEMA.extend(
            {}, extra=vol.ALLOW_EXTRA
        ),
    }
)
@websocket_api.async_response
@handle_device_errors
async def websocket_device_automation_get_condition_capabilities(hass, connection, msg):
    """Handle request for device condition capabilities."""
    condition = msg["condition"]
    capabilities = await _async_get_device_automation_capabilities(
        hass, DeviceAutomationType.CONDITION, condition
    )
    connection.send_result(msg["id"], capabilities)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "device_automation/trigger/capabilities",
        vol.Required("trigger"): DEVICE_TRIGGER_BASE_SCHEMA.extend(
            {}, extra=vol.ALLOW_EXTRA
        ),
    }
)
@websocket_api.async_response
@handle_device_errors
async def websocket_device_automation_get_trigger_capabilities(hass, connection, msg):
    """Handle request for device trigger capabilities."""
    trigger = msg["trigger"]
    capabilities = await _async_get_device_automation_capabilities(
        hass, DeviceAutomationType.TRIGGER, trigger
    )
    connection.send_result(msg["id"], capabilities)
