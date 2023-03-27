"""Switch platform for UniFi Network integration.

Support for controlling power supply of clients which are powered over Ethernet (POE).
Support for controlling network access of clients selected in option flow.
Support for controlling deep packet inspection (DPI) restriction groups.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, Generic

import aiounifi
from aiounifi.interfaces.api_handlers import ItemEvent
from aiounifi.interfaces.clients import Clients
from aiounifi.interfaces.dpi_restriction_groups import DPIRestrictionGroups
from aiounifi.interfaces.outlets import Outlets
from aiounifi.interfaces.ports import Ports
from aiounifi.models.api import ApiItemT
from aiounifi.models.client import Client, ClientBlockRequest
from aiounifi.models.device import (
    DeviceSetOutletRelayRequest,
    DeviceSetPoePortModeRequest,
)
from aiounifi.models.dpi_restriction_app import DPIRestrictionAppEnableRequest
from aiounifi.models.dpi_restriction_group import DPIRestrictionGroup
from aiounifi.models.event import Event, EventKey
from aiounifi.models.outlet import Outlet
from aiounifi.models.port import Port

from homeassistant.components.switch import (
    DOMAIN,
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceEntryType,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_MANUFACTURER, DOMAIN as UNIFI_DOMAIN
from .controller import UniFiController
from .entity import (
    HandlerT,
    SubscriptionT,
    UnifiEntity,
    UnifiEntityDescription,
    async_device_available_fn,
    async_device_device_info_fn,
)

CLIENT_BLOCKED = (EventKey.WIRED_CLIENT_BLOCKED, EventKey.WIRELESS_CLIENT_BLOCKED)
CLIENT_UNBLOCKED = (EventKey.WIRED_CLIENT_UNBLOCKED, EventKey.WIRELESS_CLIENT_UNBLOCKED)


@callback
def async_dpi_group_is_on_fn(
    controller: UniFiController, dpi_group: DPIRestrictionGroup
) -> bool:
    """Calculate if all apps are enabled."""
    api = controller.api
    return all(
        api.dpi_apps[app_id].enabled
        for app_id in dpi_group.dpiapp_ids or []
        if app_id in api.dpi_apps
    )


@callback
def async_client_device_info_fn(api: aiounifi.Controller, obj_id: str) -> DeviceInfo:
    """Create device registry entry for client."""
    client = api.clients[obj_id]
    return DeviceInfo(
        connections={(CONNECTION_NETWORK_MAC, obj_id)},
        default_manufacturer=client.oui,
        default_name=client.name or client.hostname,
    )


@callback
def async_dpi_group_device_info_fn(api: aiounifi.Controller, obj_id: str) -> DeviceInfo:
    """Create device registry entry for DPI group."""
    return DeviceInfo(
        entry_type=DeviceEntryType.SERVICE,
        identifiers={(DOMAIN, f"unifi_controller_{obj_id}")},
        manufacturer=ATTR_MANUFACTURER,
        model="UniFi Network",
        name="UniFi Network",
    )


async def async_block_client_control_fn(
    api: aiounifi.Controller, obj_id: str, target: bool
) -> None:
    """Control network access of client."""
    await api.request(ClientBlockRequest.create(obj_id, not target))


async def async_dpi_group_control_fn(
    api: aiounifi.Controller, obj_id: str, target: bool
) -> None:
    """Enable or disable DPI group."""
    dpi_group = api.dpi_groups[obj_id]
    await asyncio.gather(
        *[
            api.request(DPIRestrictionAppEnableRequest.create(app_id, target))
            for app_id in dpi_group.dpiapp_ids or []
        ]
    )


async def async_outlet_control_fn(
    api: aiounifi.Controller, obj_id: str, target: bool
) -> None:
    """Control outlet relay."""
    mac, _, index = obj_id.partition("_")
    device = api.devices[mac]
    await api.request(DeviceSetOutletRelayRequest.create(device, int(index), target))


async def async_poe_port_control_fn(
    api: aiounifi.Controller, obj_id: str, target: bool
) -> None:
    """Control poe state."""
    mac, _, index = obj_id.partition("_")
    device = api.devices[mac]
    state = "auto" if target else "off"
    await api.request(DeviceSetPoePortModeRequest.create(device, int(index), state))


@dataclass
class UnifiSwitchEntityDescriptionMixin(Generic[HandlerT, ApiItemT]):
    """Validate and load entities from different UniFi handlers."""

    control_fn: Callable[[aiounifi.Controller, str, bool], Coroutine[Any, Any, None]]
    is_on_fn: Callable[[UniFiController, ApiItemT], bool]


@dataclass
class UnifiSwitchEntityDescription(
    SwitchEntityDescription,
    UnifiEntityDescription[HandlerT, ApiItemT],
    UnifiSwitchEntityDescriptionMixin[HandlerT, ApiItemT],
):
    """Class describing UniFi switch entity."""

    custom_subscribe: Callable[[aiounifi.Controller], SubscriptionT] | None = None
    only_event_for_state_change: bool = False


ENTITY_DESCRIPTIONS: tuple[UnifiSwitchEntityDescription, ...] = (
    UnifiSwitchEntityDescription[Clients, Client](
        key="Block client",
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
        has_entity_name=True,
        icon="mdi:ethernet",
        allowed_fn=lambda controller, obj_id: obj_id in controller.option_block_clients,
        api_handler_fn=lambda api: api.clients,
        available_fn=lambda controller, obj_id: controller.available,
        control_fn=async_block_client_control_fn,
        device_info_fn=async_client_device_info_fn,
        event_is_on=CLIENT_UNBLOCKED,
        event_to_subscribe=CLIENT_BLOCKED + CLIENT_UNBLOCKED,
        is_on_fn=lambda controller, client: not client.blocked,
        name_fn=lambda client: None,
        object_fn=lambda api, obj_id: api.clients[obj_id],
        only_event_for_state_change=True,
        supported_fn=lambda controller, obj_id: True,
        unique_id_fn=lambda controller, obj_id: f"block-{obj_id}",
    ),
    UnifiSwitchEntityDescription[DPIRestrictionGroups, DPIRestrictionGroup](
        key="DPI restriction",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:network",
        allowed_fn=lambda controller, obj_id: controller.option_dpi_restrictions,
        api_handler_fn=lambda api: api.dpi_groups,
        available_fn=lambda controller, obj_id: controller.available,
        control_fn=async_dpi_group_control_fn,
        custom_subscribe=lambda api: api.dpi_apps.subscribe,
        device_info_fn=async_dpi_group_device_info_fn,
        event_is_on=None,
        event_to_subscribe=None,
        is_on_fn=async_dpi_group_is_on_fn,
        name_fn=lambda group: group.name,
        object_fn=lambda api, obj_id: api.dpi_groups[obj_id],
        supported_fn=lambda c, obj_id: bool(c.api.dpi_groups[obj_id].dpiapp_ids),
        unique_id_fn=lambda controller, obj_id: obj_id,
    ),
    UnifiSwitchEntityDescription[Outlets, Outlet](
        key="Outlet control",
        device_class=SwitchDeviceClass.OUTLET,
        has_entity_name=True,
        allowed_fn=lambda controller, obj_id: True,
        api_handler_fn=lambda api: api.outlets,
        available_fn=async_device_available_fn,
        control_fn=async_outlet_control_fn,
        device_info_fn=async_device_device_info_fn,
        event_is_on=None,
        event_to_subscribe=None,
        is_on_fn=lambda controller, outlet: outlet.relay_state,
        name_fn=lambda outlet: outlet.name,
        object_fn=lambda api, obj_id: api.outlets[obj_id],
        supported_fn=lambda c, obj_id: c.api.outlets[obj_id].has_relay,
        unique_id_fn=lambda controller, obj_id: f"{obj_id.split('_', 1)[0]}-outlet-{obj_id.split('_', 1)[1]}",
    ),
    UnifiSwitchEntityDescription[Ports, Port](
        key="PoE port control",
        device_class=SwitchDeviceClass.OUTLET,
        entity_category=EntityCategory.CONFIG,
        has_entity_name=True,
        entity_registry_enabled_default=False,
        icon="mdi:ethernet",
        allowed_fn=lambda controller, obj_id: True,
        api_handler_fn=lambda api: api.ports,
        available_fn=async_device_available_fn,
        control_fn=async_poe_port_control_fn,
        device_info_fn=async_device_device_info_fn,
        event_is_on=None,
        event_to_subscribe=None,
        is_on_fn=lambda controller, port: port.poe_mode != "off",
        name_fn=lambda port: f"{port.name} PoE",
        object_fn=lambda api, obj_id: api.ports[obj_id],
        supported_fn=lambda controller, obj_id: controller.api.ports[obj_id].port_poe,
        unique_id_fn=lambda controller, obj_id: f"{obj_id.split('_', 1)[0]}-poe-{obj_id.split('_', 1)[1]}",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches for UniFi Network integration."""
    controller: UniFiController = hass.data[UNIFI_DOMAIN][config_entry.entry_id]

    if controller.site_role != "admin":
        return

    for mac in controller.option_block_clients:
        if mac not in controller.api.clients and mac in controller.api.clients_all:
            controller.api.clients.process_raw(
                [dict(controller.api.clients_all[mac].raw)]
            )

    controller.register_platform_add_entities(
        UnifiSwitchEntity, ENTITY_DESCRIPTIONS, async_add_entities
    )


class UnifiSwitchEntity(UnifiEntity[HandlerT, ApiItemT], SwitchEntity):
    """Base representation of a UniFi switch."""

    entity_description: UnifiSwitchEntityDescription[HandlerT, ApiItemT]
    only_event_for_state_change = False

    @callback
    def async_initiate_state(self) -> None:
        """Initiate entity state."""
        self.async_update_state(ItemEvent.ADDED, self._obj_id)
        self.only_event_for_state_change = (
            self.entity_description.only_event_for_state_change
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on switch."""
        await self.entity_description.control_fn(
            self.controller.api, self._obj_id, True
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off switch."""
        await self.entity_description.control_fn(
            self.controller.api, self._obj_id, False
        )

    @callback
    def async_update_state(self, event: ItemEvent, obj_id: str) -> None:
        """Update entity state.

        Update attr_is_on.
        """
        if self.only_event_for_state_change:
            return

        description = self.entity_description
        obj = description.object_fn(self.controller.api, self._obj_id)
        if (is_on := description.is_on_fn(self.controller, obj)) != self.is_on:
            self._attr_is_on = is_on

    @callback
    def async_event_callback(self, event: Event) -> None:
        """Event subscription callback."""
        if event.mac != self._obj_id:
            return

        description = self.entity_description
        assert isinstance(description.event_to_subscribe, tuple)
        assert isinstance(description.event_is_on, tuple)

        if event.key in description.event_to_subscribe:
            self._attr_is_on = event.key in description.event_is_on
        self._attr_available = description.available_fn(self.controller, self._obj_id)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        await super().async_added_to_hass()

        if self.entity_description.custom_subscribe is not None:
            self.async_on_remove(
                self.entity_description.custom_subscribe(self.controller.api)(
                    self.async_signalling_callback, ItemEvent.CHANGED
                ),
            )
