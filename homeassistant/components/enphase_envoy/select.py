"""Select platform for Enphase Envoy solar energy monitor."""
from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from pyenphase import Envoy, EnvoyDryContactSettings
from pyenphase.models.dry_contacts import DryContactAction, DryContactMode

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EnphaseUpdateCoordinator
from .entity import EnvoyBaseEntity


@dataclass
class EnvoyRelayRequiredKeysMixin:
    """Mixin for required keys."""

    value_fn: Callable[[EnvoyDryContactSettings], str]
    update_fn: Callable[
        [Envoy, EnvoyDryContactSettings, str], Coroutine[Any, Any, dict[str, Any]]
    ]


@dataclass
class EnvoyRelaySelectEntityDescription(
    SelectEntityDescription, EnvoyRelayRequiredKeysMixin
):
    """Describes an Envoy Dry Contact Relay select entity."""


RELAY_MODE_MAP = {
    DryContactMode.MANUAL: "standard",
    DryContactMode.STATE_OF_CHARGE: "battery",
}
REVERSE_RELAY_MODE_MAP = {v: k for k, v in RELAY_MODE_MAP.items()}
RELAY_ACTION_MAP = {
    DryContactAction.APPLY: "powered",
    DryContactAction.SHED: "not_powered",
    DryContactAction.SCHEDULE: "schedule",
    DryContactAction.NONE: "none",
}
REVERSE_RELAY_ACTION_MAP = {v: k for k, v in RELAY_ACTION_MAP.items()}
MODE_OPTIONS = list(REVERSE_RELAY_MODE_MAP)
ACTION_OPTIONS = list(REVERSE_RELAY_ACTION_MAP)

RELAY_ENTITIES = (
    EnvoyRelaySelectEntityDescription(
        key="mode",
        translation_key="relay_mode",
        options=MODE_OPTIONS,
        value_fn=lambda relay: RELAY_MODE_MAP[relay.mode],
        update_fn=lambda envoy, relay, value: envoy.update_dry_contact(
            {
                "id": relay.id,
                "mode": REVERSE_RELAY_MODE_MAP[value],
            }
        ),
    ),
    EnvoyRelaySelectEntityDescription(
        key="grid_action",
        translation_key="relay_grid_action",
        options=ACTION_OPTIONS,
        value_fn=lambda relay: RELAY_ACTION_MAP[relay.grid_action],
        update_fn=lambda envoy, relay, value: envoy.update_dry_contact(
            {
                "id": relay.id,
                "grid_action": REVERSE_RELAY_ACTION_MAP[value],
            }
        ),
    ),
    EnvoyRelaySelectEntityDescription(
        key="microgrid_action",
        translation_key="relay_microgrid_action",
        options=ACTION_OPTIONS,
        value_fn=lambda relay: RELAY_ACTION_MAP[relay.micro_grid_action],
        update_fn=lambda envoy, relay, value: envoy.update_dry_contact(
            {
                "id": relay.id,
                "micro_grid_action": REVERSE_RELAY_ACTION_MAP[value],
            }
        ),
    ),
    EnvoyRelaySelectEntityDescription(
        key="generator_action",
        translation_key="relay_generator_action",
        options=ACTION_OPTIONS,
        value_fn=lambda relay: RELAY_ACTION_MAP[relay.generator_action],
        update_fn=lambda envoy, relay, value: envoy.update_dry_contact(
            {
                "id": relay.id,
                "generator_action": REVERSE_RELAY_ACTION_MAP[value],
            }
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Enphase Envoy select platform."""
    coordinator: EnphaseUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    envoy_data = coordinator.envoy.data
    assert envoy_data is not None
    entities: list[SelectEntity] = []
    if envoy_data.dry_contact_settings:
        entities.extend(
            EnvoyRelaySelectEntity(coordinator, entity, relay)
            for entity in RELAY_ENTITIES
            for relay in envoy_data.dry_contact_settings
        )
    async_add_entities(entities)


class EnvoyRelaySelectEntity(EnvoyBaseEntity, SelectEntity):
    """Representation of an Enphase Enpower select entity."""

    entity_description: EnvoyRelaySelectEntityDescription

    def __init__(
        self,
        coordinator: EnphaseUpdateCoordinator,
        description: EnvoyRelaySelectEntityDescription,
        relay_id: str,
    ) -> None:
        """Initialize the Enphase relay select entity."""
        super().__init__(coordinator, description)
        self.envoy = coordinator.envoy
        enpower = self.data.enpower
        assert enpower is not None
        serial_number = enpower.serial_number
        self._relay_id = relay_id
        self._attr_unique_id = f"{serial_number}_relay_{relay_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, relay_id)},
            manufacturer="Enphase",
            model="Dry contact relay",
            name=self.relay.load_name,
            sw_version=str(enpower.firmware_version),
            via_device=(DOMAIN, serial_number),
        )

    @property
    def relay(self) -> EnvoyDryContactSettings:
        """Return the relay object."""
        return self.data.dry_contact_settings[self._relay_id]

    @property
    def current_option(self) -> str:
        """Return the state of the Enpower switch."""
        return self.entity_description.value_fn(self.relay)

    async def async_select_option(self, option: str) -> None:
        """Update the relay."""
        await self.entity_description.update_fn(self.envoy, self.relay, option)
        await self.coordinator.async_request_refresh()
