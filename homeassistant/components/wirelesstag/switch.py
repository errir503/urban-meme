"""Switch implementation for Wireless Sensor Tags (wirelesstag.net)."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.switch import (
    PLATFORM_SCHEMA,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.const import CONF_MONITORED_CONDITIONS
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import DOMAIN as WIRELESSTAG_DOMAIN, WirelessTagBaseSensor

SWITCH_TYPES: tuple[SwitchEntityDescription, ...] = (
    SwitchEntityDescription(
        key="temperature",
        name="Arm Temperature",
    ),
    SwitchEntityDescription(
        key="humidity",
        name="Arm Humidity",
    ),
    SwitchEntityDescription(
        key="motion",
        name="Arm Motion",
    ),
    SwitchEntityDescription(
        key="light",
        name="Arm Light",
    ),
    SwitchEntityDescription(
        key="moisture",
        name="Arm Moisture",
    ),
)

SWITCH_KEYS: list[str] = [desc.key for desc in SWITCH_TYPES]

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_MONITORED_CONDITIONS, default=[]): vol.All(
            cv.ensure_list, [vol.In(SWITCH_KEYS)]
        )
    }
)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up switches for a Wireless Sensor Tags."""
    platform = hass.data[WIRELESSTAG_DOMAIN]

    tags = platform.load_tags()
    monitored_conditions = config[CONF_MONITORED_CONDITIONS]
    entities = [
        WirelessTagSwitch(platform, tag, description)
        for tag in tags.values()
        for description in SWITCH_TYPES
        if description.key in monitored_conditions
        and description.key in tag.allowed_monitoring_types
    ]

    add_entities(entities, True)


class WirelessTagSwitch(WirelessTagBaseSensor, SwitchEntity):
    """A switch implementation for Wireless Sensor Tags."""

    def __init__(self, api, tag, description: SwitchEntityDescription) -> None:
        """Initialize a switch for Wireless Sensor Tag."""
        super().__init__(api, tag)
        self.entity_description = description
        self._name = f"{self._tag.name} {description.name}"
        self._attr_unique_id = f"{self.tag_id}_{description.key}"

    def turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        self._api.arm(self)

    def turn_off(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        self._api.disarm(self)

    @property
    def is_on(self) -> bool:
        """Return True if entity is on."""
        return self._state

    def updated_state_value(self):
        """Provide formatted value."""
        return self.principal_value

    @property
    def principal_value(self):
        """Provide actual value of switch."""
        attr_name = f"is_{self.entity_description.key}_sensor_armed"
        return getattr(self._tag, attr_name, False)
