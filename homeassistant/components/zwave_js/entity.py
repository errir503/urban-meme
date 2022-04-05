"""Generic Z-Wave Entity Class."""
from __future__ import annotations

import logging

from zwave_js_server.client import Client as ZwaveClient
from zwave_js_server.const import NodeStatus
from zwave_js_server.model.value import Value as ZwaveValue, get_value_id

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, Entity

from .const import DOMAIN
from .discovery import ZwaveDiscoveryInfo
from .helpers import get_device_id, get_unique_id
from .migrate import async_add_migration_entity_value

LOGGER = logging.getLogger(__name__)

EVENT_VALUE_UPDATED = "value updated"
EVENT_VALUE_REMOVED = "value removed"
EVENT_DEAD = "dead"
EVENT_ALIVE = "alive"


class ZWaveBaseEntity(Entity):
    """Generic Entity Class for a Z-Wave Device."""

    _attr_should_poll = False

    def __init__(
        self, config_entry: ConfigEntry, client: ZwaveClient, info: ZwaveDiscoveryInfo
    ) -> None:
        """Initialize a generic Z-Wave device entity."""
        self.config_entry = config_entry
        self.client = client
        self.info = info
        # entities requiring additional values, can add extra ids to this list
        self.watched_value_ids = {self.info.primary_value.value_id}

        if self.info.additional_value_ids_to_watch:
            self.watched_value_ids = self.watched_value_ids.union(
                self.info.additional_value_ids_to_watch
            )

        # Entity class attributes
        self._attr_name = self.generate_name()
        self._attr_unique_id = get_unique_id(
            self.client, self.info.primary_value.value_id
        )
        self._attr_entity_registry_enabled_default = (
            self.info.entity_registry_enabled_default
        )
        self._attr_assumed_state = self.info.assumed_state
        # device is precreated in main handler
        self._attr_device_info = DeviceInfo(
            identifiers={get_device_id(self.client, self.info.node)},
        )

    @callback
    def on_value_update(self) -> None:
        """Call when one of the watched values change.

        To be overridden by platforms needing this event.
        """

    async def async_poll_value(self, refresh_all_values: bool) -> None:
        """Poll a value."""
        if not refresh_all_values:
            self.hass.async_create_task(
                self.info.node.async_poll_value(self.info.primary_value)
            )
            LOGGER.info(
                (
                    "Refreshing primary value %s for %s, "
                    "state update may be delayed for devices on battery"
                ),
                self.info.primary_value,
                self.entity_id,
            )
            return

        for value_id in self.watched_value_ids:
            self.hass.async_create_task(self.info.node.async_poll_value(value_id))

        LOGGER.info(
            (
                "Refreshing values %s for %s, state update may be delayed for "
                "devices on battery"
            ),
            ", ".join(self.watched_value_ids),
            self.entity_id,
        )

    async def async_added_to_hass(self) -> None:
        """Call when entity is added."""
        # Add value_changed callbacks.
        self.async_on_remove(
            self.info.node.on(EVENT_VALUE_UPDATED, self._value_changed)
        )
        self.async_on_remove(
            self.info.node.on(EVENT_VALUE_REMOVED, self._value_removed)
        )

        for status_event in (EVENT_ALIVE, EVENT_DEAD):
            self.async_on_remove(
                self.info.node.on(status_event, self._node_status_alive_or_dead)
            )

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_{self.unique_id}_poll_value",
                self.async_poll_value,
            )
        )

        # Add legacy Z-Wave migration data.
        await async_add_migration_entity_value(
            self.hass, self.config_entry, self.entity_id, self.info
        )

    def generate_name(
        self,
        include_value_name: bool = False,
        alternate_value_name: str | None = None,
        additional_info: list[str] | None = None,
        name_suffix: str | None = None,
    ) -> str:
        """Generate entity name."""
        if additional_info is None:
            additional_info = []
        name: str = (
            self.info.node.name
            or self.info.node.device_config.description
            or f"Node {self.info.node.node_id}"
        )
        if name_suffix:
            name = f"{name} {name_suffix}"
        if include_value_name:
            value_name = (
                alternate_value_name
                or self.info.primary_value.metadata.label
                or self.info.primary_value.property_key_name
                or self.info.primary_value.property_name
            )
            name = f"{name}: {value_name}"
        for item in additional_info:
            if item:
                name += f" - {item}"
        # append endpoint if > 1
        if self.info.primary_value.endpoint > 1:
            name += f" ({self.info.primary_value.endpoint})"

        return name

    @property
    def available(self) -> bool:
        """Return entity availability."""
        return (
            self.client.connected
            and bool(self.info.node.ready)
            and self.info.node.status != NodeStatus.DEAD
        )

    @callback
    def _node_status_alive_or_dead(self, event_data: dict) -> None:
        """
        Call when node status changes to alive or dead.

        Should not be overridden by subclasses.
        """
        self.async_write_ha_state()

    @callback
    def _value_changed(self, event_data: dict) -> None:
        """Call when a value associated with our node changes.

        Should not be overridden by subclasses.
        """
        value_id = event_data["value"].value_id

        if value_id not in self.watched_value_ids:
            return

        value = self.info.node.values[value_id]

        LOGGER.debug(
            "[%s] Value %s/%s changed to: %s",
            self.entity_id,
            value.property_,
            value.property_key_name,
            value.value,
        )

        self.on_value_update()
        self.async_write_ha_state()

    @callback
    def _value_removed(self, event_data: dict) -> None:
        """Call when a value associated with our node is removed.

        Should not be overridden by subclasses.
        """
        value_id = event_data["value"].value_id

        if value_id != self.info.primary_value.value_id:
            return

        LOGGER.debug(
            "[%s] Primary value %s is being removed",
            self.entity_id,
            value_id,
        )

        self.hass.async_create_task(self.async_remove())

    @callback
    def get_zwave_value(
        self,
        value_property: str | int,
        command_class: int | None = None,
        endpoint: int | None = None,
        value_property_key: int | str | None = None,
        add_to_watched_value_ids: bool = True,
        check_all_endpoints: bool = False,
    ) -> ZwaveValue | None:
        """Return specific ZwaveValue on this ZwaveNode."""
        # use commandclass and endpoint from primary value if omitted
        return_value = None
        if command_class is None:
            command_class = self.info.primary_value.command_class
        if endpoint is None:
            endpoint = self.info.primary_value.endpoint

        # lookup value by value_id
        value_id = get_value_id(
            self.info.node,
            command_class,
            value_property,
            endpoint=endpoint,
            property_key=value_property_key,
        )
        return_value = self.info.node.values.get(value_id)

        # If we haven't found a value and check_all_endpoints is True, we should
        # return the first value we can find on any other endpoint
        if return_value is None and check_all_endpoints:
            for endpoint_idx in self.info.node.endpoints:
                if endpoint_idx != self.info.primary_value.endpoint:
                    value_id = get_value_id(
                        self.info.node,
                        command_class,
                        value_property,
                        endpoint=endpoint_idx,
                        property_key=value_property_key,
                    )
                    return_value = self.info.node.values.get(value_id)
                    if return_value:
                        break

        # add to watched_ids list so we will be triggered when the value updates
        if (
            return_value
            and return_value.value_id not in self.watched_value_ids
            and add_to_watched_value_ids
        ):
            self.watched_value_ids.add(return_value.value_id)
        return return_value
