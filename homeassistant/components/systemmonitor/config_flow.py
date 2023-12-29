"""Adds config flow for System Monitor."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.components.homeassistant import DOMAIN as HOMEASSISTANT_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaCommonFlowHandler,
    SchemaConfigFlowHandler,
    SchemaFlowFormStep,
)
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.util import slugify

from .const import CONF_PROCESS, DOMAIN
from .util import get_all_running_processes


async def validate_sensor_setup(
    handler: SchemaCommonFlowHandler, user_input: dict[str, Any]
) -> dict[str, Any]:
    """Validate sensor input."""
    # Standard behavior is to merge the result with the options.
    # In this case, we want to add a sub-item so we update the options directly.
    sensors: dict[str, list] = handler.options.setdefault(SENSOR_DOMAIN, {})
    processes = sensors.setdefault(CONF_PROCESS, [])
    previous_processes = processes.copy()
    processes.clear()
    processes.extend(user_input[CONF_PROCESS])

    entity_registry = er.async_get(handler.parent_handler.hass)
    for process in previous_processes:
        if process not in processes and (
            entity_id := entity_registry.async_get_entity_id(
                SENSOR_DOMAIN, DOMAIN, slugify(f"process_{process}")
            )
        ):
            entity_registry.async_remove(entity_id)

    return {}


async def validate_import_sensor_setup(
    handler: SchemaCommonFlowHandler, user_input: dict[str, Any]
) -> dict[str, Any]:
    """Validate sensor input."""
    # Standard behavior is to merge the result with the options.
    # In this case, we want to add a sub-item so we update the options directly.
    sensors: dict[str, list] = handler.options.setdefault(SENSOR_DOMAIN, {})
    import_processes: list[str] = user_input["processes"]
    processes = sensors.setdefault(CONF_PROCESS, [])
    processes.extend(import_processes)
    legacy_resources: list[str] = handler.options.setdefault("resources", [])
    legacy_resources.extend(user_input["legacy_resources"])

    async_create_issue(
        handler.parent_handler.hass,
        HOMEASSISTANT_DOMAIN,
        f"deprecated_yaml_{DOMAIN}",
        breaks_in_ha_version="2024.7.0",
        is_fixable=False,
        is_persistent=False,
        issue_domain=DOMAIN,
        severity=IssueSeverity.WARNING,
        translation_key="deprecated_yaml",
        translation_placeholders={
            "domain": DOMAIN,
            "integration_title": "System Monitor",
        },
    )
    return {}


async def get_sensor_setup_schema(handler: SchemaCommonFlowHandler) -> vol.Schema:
    """Return process sensor setup schema."""
    hass = handler.parent_handler.hass
    processes = await hass.async_add_executor_job(get_all_running_processes)
    return vol.Schema(
        {
            vol.Required(CONF_PROCESS): SelectSelector(
                SelectSelectorConfig(
                    options=processes,
                    multiple=True,
                    custom_value=True,
                    mode=SelectSelectorMode.DROPDOWN,
                    sort=True,
                )
            )
        }
    )


async def get_suggested_value(handler: SchemaCommonFlowHandler) -> dict[str, Any]:
    """Return suggested values for sensor setup."""
    sensors: dict[str, list] = handler.options.get(SENSOR_DOMAIN, {})
    processes: list[str] = sensors.get(CONF_PROCESS, [])
    return {CONF_PROCESS: processes}


CONFIG_FLOW = {
    "user": SchemaFlowFormStep(schema=vol.Schema({})),
    "import": SchemaFlowFormStep(
        schema=vol.Schema({}),
        validate_user_input=validate_import_sensor_setup,
    ),
}
OPTIONS_FLOW = {
    "init": SchemaFlowFormStep(
        get_sensor_setup_schema,
        suggested_values=get_suggested_value,
        validate_user_input=validate_sensor_setup,
    )
}


class SystemMonitorConfigFlowHandler(SchemaConfigFlowHandler, domain=DOMAIN):
    """Handle a config flow for System Monitor."""

    config_flow = CONFIG_FLOW
    options_flow = OPTIONS_FLOW

    def async_config_entry_title(self, options: Mapping[str, Any]) -> str:
        """Return config entry title."""
        return "System Monitor"

    @callback
    def async_create_entry(self, data: Mapping[str, Any], **kwargs: Any) -> FlowResult:
        """Finish config flow and create a config entry."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        return super().async_create_entry(data, **kwargs)
