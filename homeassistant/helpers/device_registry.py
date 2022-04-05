"""Provide a way to connect entities belonging to one device."""
from __future__ import annotations

from collections import OrderedDict
import logging
import time
from typing import TYPE_CHECKING, Any, NamedTuple, cast

import attr

from homeassistant.backports.enum import StrEnum
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, RequiredParameterMissing
from homeassistant.loader import bind_hass
import homeassistant.util.uuid as uuid_util

from . import storage
from .debounce import Debouncer
from .frame import report
from .typing import UNDEFINED, UndefinedType

# mypy: disallow_any_generics

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from . import entity_registry

_LOGGER = logging.getLogger(__name__)

DATA_REGISTRY = "device_registry"
EVENT_DEVICE_REGISTRY_UPDATED = "device_registry_updated"
STORAGE_KEY = "core.device_registry"
STORAGE_VERSION_MAJOR = 1
STORAGE_VERSION_MINOR = 3
SAVE_DELAY = 10
CLEANUP_DELAY = 10

CONNECTION_NETWORK_MAC = "mac"
CONNECTION_UPNP = "upnp"
CONNECTION_ZIGBEE = "zigbee"

ORPHANED_DEVICE_KEEP_SECONDS = 86400 * 30

RUNTIME_ONLY_ATTRS = {"suggested_area"}


class _DeviceIndex(NamedTuple):
    identifiers: dict[tuple[str, str], str]
    connections: dict[tuple[str, str], str]


class DeviceEntryDisabler(StrEnum):
    """What disabled a device entry."""

    CONFIG_ENTRY = "config_entry"
    INTEGRATION = "integration"
    USER = "user"


# DISABLED_* are deprecated, to be removed in 2022.3
DISABLED_CONFIG_ENTRY = DeviceEntryDisabler.CONFIG_ENTRY.value
DISABLED_INTEGRATION = DeviceEntryDisabler.INTEGRATION.value
DISABLED_USER = DeviceEntryDisabler.USER.value


class DeviceEntryType(StrEnum):
    """Device entry type."""

    SERVICE = "service"


@attr.s(slots=True, frozen=True)
class DeviceEntry:
    """Device Registry Entry."""

    area_id: str | None = attr.ib(default=None)
    config_entries: set[str] = attr.ib(converter=set, factory=set)
    configuration_url: str | None = attr.ib(default=None)
    connections: set[tuple[str, str]] = attr.ib(converter=set, factory=set)
    disabled_by: DeviceEntryDisabler | None = attr.ib(default=None)
    entry_type: DeviceEntryType | None = attr.ib(default=None)
    id: str = attr.ib(factory=uuid_util.random_uuid_hex)
    identifiers: set[tuple[str, str]] = attr.ib(converter=set, factory=set)
    manufacturer: str | None = attr.ib(default=None)
    model: str | None = attr.ib(default=None)
    name_by_user: str | None = attr.ib(default=None)
    name: str | None = attr.ib(default=None)
    suggested_area: str | None = attr.ib(default=None)
    sw_version: str | None = attr.ib(default=None)
    hw_version: str | None = attr.ib(default=None)
    via_device_id: str | None = attr.ib(default=None)
    # This value is not stored, just used to keep track of events to fire.
    is_new: bool = attr.ib(default=False)

    @property
    def disabled(self) -> bool:
        """Return if entry is disabled."""
        return self.disabled_by is not None


@attr.s(slots=True, frozen=True)
class DeletedDeviceEntry:
    """Deleted Device Registry Entry."""

    config_entries: set[str] = attr.ib()
    connections: set[tuple[str, str]] = attr.ib()
    identifiers: set[tuple[str, str]] = attr.ib()
    id: str = attr.ib()
    orphaned_timestamp: float | None = attr.ib()

    def to_device_entry(
        self,
        config_entry_id: str,
        connections: set[tuple[str, str]],
        identifiers: set[tuple[str, str]],
    ) -> DeviceEntry:
        """Create DeviceEntry from DeletedDeviceEntry."""
        return DeviceEntry(
            # type ignores: likely https://github.com/python/mypy/issues/8625
            config_entries={config_entry_id},  # type: ignore[arg-type]
            connections=self.connections & connections,  # type: ignore[arg-type]
            identifiers=self.identifiers & identifiers,  # type: ignore[arg-type]
            id=self.id,
            is_new=True,
        )


def format_mac(mac: str) -> str:
    """Format the mac address string for entry into dev reg."""
    to_test = mac

    if len(to_test) == 17 and to_test.count(":") == 5:
        return to_test.lower()

    if len(to_test) == 17 and to_test.count("-") == 5:
        to_test = to_test.replace("-", "")
    elif len(to_test) == 14 and to_test.count(".") == 2:
        to_test = to_test.replace(".", "")

    if len(to_test) == 12:
        # no : included
        return ":".join(to_test.lower()[i : i + 2] for i in range(0, 12, 2))

    # Not sure how formatted, return original
    return mac


def _async_get_device_id_from_index(
    devices_index: _DeviceIndex,
    identifiers: set[tuple[str, str]],
    connections: set[tuple[str, str]] | None,
) -> str | None:
    """Check if device has previously been registered."""
    for identifier in identifiers:
        if identifier in devices_index.identifiers:
            return devices_index.identifiers[identifier]
    if not connections:
        return None
    for connection in _normalize_connections(connections):
        if connection in devices_index.connections:
            return devices_index.connections[connection]
    return None


class DeviceRegistryStore(storage.Store):
    """Store entity registry data."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Migrate to the new version."""
        if old_major_version < 2:
            if old_minor_version < 2:
                # From version 1.1
                for device in old_data["devices"]:
                    # Introduced in 0.110
                    try:
                        device["entry_type"] = DeviceEntryType(device.get("entry_type"))
                    except ValueError:
                        device["entry_type"] = None

                    # Introduced in 0.79
                    # renamed in 0.95
                    device["via_device_id"] = device.get("via_device_id") or device.get(
                        "hub_device_id"
                    )
                    # Introduced in 0.87
                    device["area_id"] = device.get("area_id")
                    device["name_by_user"] = device.get("name_by_user")
                    # Introduced in 0.119
                    device["disabled_by"] = device.get("disabled_by")
                    # Introduced in 2021.11
                    device["configuration_url"] = device.get("configuration_url")
                # Introduced in 0.111
                old_data["deleted_devices"] = old_data.get("deleted_devices", [])
                for device in old_data["deleted_devices"]:
                    # Introduced in 2021.2
                    device["orphaned_timestamp"] = device.get("orphaned_timestamp")
            if old_minor_version < 3:
                # Introduced in 2022.2
                for device in old_data["devices"]:
                    device["hw_version"] = device.get("hw_version")

        if old_major_version > 1:
            raise NotImplementedError
        return old_data


class DeviceRegistry:
    """Class to hold a registry of devices."""

    devices: dict[str, DeviceEntry]
    deleted_devices: dict[str, DeletedDeviceEntry]
    _registered_index: _DeviceIndex
    _deleted_index: _DeviceIndex

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the device registry."""
        self.hass = hass
        self._store = DeviceRegistryStore(
            hass,
            STORAGE_VERSION_MAJOR,
            STORAGE_KEY,
            atomic_writes=True,
            minor_version=STORAGE_VERSION_MINOR,
        )
        self._clear_index()

    @callback
    def async_get(self, device_id: str) -> DeviceEntry | None:
        """Get device."""
        return self.devices.get(device_id)

    @callback
    def async_get_device(
        self,
        identifiers: set[tuple[str, str]],
        connections: set[tuple[str, str]] | None = None,
    ) -> DeviceEntry | None:
        """Check if device is registered."""
        device_id = _async_get_device_id_from_index(
            self._registered_index, identifiers, connections
        )
        if device_id is None:
            return None
        return self.devices[device_id]

    def _async_get_deleted_device(
        self,
        identifiers: set[tuple[str, str]],
        connections: set[tuple[str, str]] | None,
    ) -> DeletedDeviceEntry | None:
        """Check if device is deleted."""
        device_id = _async_get_device_id_from_index(
            self._deleted_index, identifiers, connections
        )
        if device_id is None:
            return None
        return self.deleted_devices[device_id]

    def _add_device(self, device: DeviceEntry | DeletedDeviceEntry) -> None:
        """Add a device and index it."""
        if isinstance(device, DeletedDeviceEntry):
            devices_index = self._deleted_index
            self.deleted_devices[device.id] = device
        else:
            devices_index = self._registered_index
            self.devices[device.id] = device

        _add_device_to_index(devices_index, device)

    def _remove_device(self, device: DeviceEntry | DeletedDeviceEntry) -> None:
        """Remove a device and remove it from the index."""
        if isinstance(device, DeletedDeviceEntry):
            devices_index = self._deleted_index
            self.deleted_devices.pop(device.id)
        else:
            devices_index = self._registered_index
            self.devices.pop(device.id)

        _remove_device_from_index(devices_index, device)

    def _update_device(self, old_device: DeviceEntry, new_device: DeviceEntry) -> None:
        """Update a device and the index."""
        self.devices[new_device.id] = new_device

        devices_index = self._registered_index
        _remove_device_from_index(devices_index, old_device)
        _add_device_to_index(devices_index, new_device)

    def _clear_index(self) -> None:
        """Clear the index."""
        self._registered_index = _DeviceIndex(identifiers={}, connections={})
        self._deleted_index = _DeviceIndex(identifiers={}, connections={})

    def _rebuild_index(self) -> None:
        """Create the index after loading devices."""
        self._clear_index()
        for device in self.devices.values():
            _add_device_to_index(self._registered_index, device)
        for deleted_device in self.deleted_devices.values():
            _add_device_to_index(self._deleted_index, deleted_device)

    @callback
    def async_get_or_create(
        self,
        *,
        config_entry_id: str,
        configuration_url: str | None | UndefinedType = UNDEFINED,
        connections: set[tuple[str, str]] | None = None,
        default_manufacturer: str | None | UndefinedType = UNDEFINED,
        default_model: str | None | UndefinedType = UNDEFINED,
        default_name: str | None | UndefinedType = UNDEFINED,
        # To disable a device if it gets created
        disabled_by: DeviceEntryDisabler | None | UndefinedType = UNDEFINED,
        entry_type: DeviceEntryType | None | UndefinedType = UNDEFINED,
        identifiers: set[tuple[str, str]] | None = None,
        manufacturer: str | None | UndefinedType = UNDEFINED,
        model: str | None | UndefinedType = UNDEFINED,
        name: str | None | UndefinedType = UNDEFINED,
        suggested_area: str | None | UndefinedType = UNDEFINED,
        sw_version: str | None | UndefinedType = UNDEFINED,
        hw_version: str | None | UndefinedType = UNDEFINED,
        via_device: tuple[str, str] | None = None,
    ) -> DeviceEntry:
        """Get device. Create if it doesn't exist."""
        if not identifiers and not connections:
            raise RequiredParameterMissing(["identifiers", "connections"])

        if identifiers is None:
            identifiers = set()

        if connections is None:
            connections = set()
        else:
            connections = _normalize_connections(connections)

        device = self.async_get_device(identifiers, connections)

        if device is None:
            deleted_device = self._async_get_deleted_device(identifiers, connections)
            if deleted_device is None:
                device = DeviceEntry(is_new=True)
            else:
                self._remove_device(deleted_device)
                device = deleted_device.to_device_entry(
                    config_entry_id, connections, identifiers
                )
            self._add_device(device)

        if default_manufacturer is not UNDEFINED and device.manufacturer is None:
            manufacturer = default_manufacturer

        if default_model is not UNDEFINED and device.model is None:
            model = default_model

        if default_name is not UNDEFINED and device.name is None:
            name = default_name

        if via_device is not None:
            via = self.async_get_device({via_device})
            via_device_id: str | UndefinedType = via.id if via else UNDEFINED
        else:
            via_device_id = UNDEFINED

        if isinstance(entry_type, str) and not isinstance(entry_type, DeviceEntryType):
            report(  # type: ignore[unreachable]
                "uses str for device registry entry_type. This is deprecated and will "
                "stop working in Home Assistant 2022.3, it should be updated to use "
                "DeviceEntryType instead",
                error_if_core=False,
            )
            entry_type = DeviceEntryType(entry_type)

        device = self.async_update_device(
            device.id,
            add_config_entry_id=config_entry_id,
            configuration_url=configuration_url,
            disabled_by=disabled_by,
            entry_type=entry_type,
            manufacturer=manufacturer,
            merge_connections=connections or UNDEFINED,
            merge_identifiers=identifiers or UNDEFINED,
            model=model,
            name=name,
            suggested_area=suggested_area,
            sw_version=sw_version,
            hw_version=hw_version,
            via_device_id=via_device_id,
        )

        # This is safe because _async_update_device will always return a device
        # in this use case.
        assert device
        return device

    @callback
    def async_update_device(
        self,
        device_id: str,
        *,
        add_config_entry_id: str | UndefinedType = UNDEFINED,
        area_id: str | None | UndefinedType = UNDEFINED,
        configuration_url: str | None | UndefinedType = UNDEFINED,
        disabled_by: DeviceEntryDisabler | None | UndefinedType = UNDEFINED,
        entry_type: DeviceEntryType | None | UndefinedType = UNDEFINED,
        manufacturer: str | None | UndefinedType = UNDEFINED,
        merge_connections: set[tuple[str, str]] | UndefinedType = UNDEFINED,
        merge_identifiers: set[tuple[str, str]] | UndefinedType = UNDEFINED,
        model: str | None | UndefinedType = UNDEFINED,
        name_by_user: str | None | UndefinedType = UNDEFINED,
        name: str | None | UndefinedType = UNDEFINED,
        new_identifiers: set[tuple[str, str]] | UndefinedType = UNDEFINED,
        remove_config_entry_id: str | UndefinedType = UNDEFINED,
        suggested_area: str | None | UndefinedType = UNDEFINED,
        sw_version: str | None | UndefinedType = UNDEFINED,
        hw_version: str | None | UndefinedType = UNDEFINED,
        via_device_id: str | None | UndefinedType = UNDEFINED,
    ) -> DeviceEntry | None:
        """Update device attributes."""
        old = self.devices[device_id]

        new_values: dict[str, Any] = {}  # Dict with new key/value pairs
        old_values: dict[str, Any] = {}  # Dict with old key/value pairs

        config_entries = old.config_entries

        if merge_identifiers is not UNDEFINED and new_identifiers is not UNDEFINED:
            raise HomeAssistantError()

        if isinstance(disabled_by, str) and not isinstance(
            disabled_by, DeviceEntryDisabler
        ):
            report(  # type: ignore[unreachable]
                "uses str for device registry disabled_by. This is deprecated and will "
                "stop working in Home Assistant 2022.3, it should be updated to use "
                "DeviceEntryDisabler instead",
                error_if_core=False,
            )
            disabled_by = DeviceEntryDisabler(disabled_by)

        if (
            suggested_area not in (UNDEFINED, None, "")
            and area_id is UNDEFINED
            and old.area_id is None
        ):
            area = self.hass.helpers.area_registry.async_get(
                self.hass
            ).async_get_or_create(suggested_area)
            area_id = area.id

        if (
            add_config_entry_id is not UNDEFINED
            and add_config_entry_id not in old.config_entries
        ):
            config_entries = old.config_entries | {add_config_entry_id}

        if (
            remove_config_entry_id is not UNDEFINED
            and remove_config_entry_id in config_entries
        ):
            if config_entries == {remove_config_entry_id}:
                self.async_remove_device(device_id)
                return None

            config_entries = config_entries - {remove_config_entry_id}

        if config_entries != old.config_entries:
            new_values["config_entries"] = config_entries
            old_values["config_entries"] = old.config_entries

        for attr_name, setvalue in (
            ("connections", merge_connections),
            ("identifiers", merge_identifiers),
        ):
            old_value = getattr(old, attr_name)
            # If not undefined, check if `value` contains new items.
            if setvalue is not UNDEFINED and not setvalue.issubset(old_value):
                new_values[attr_name] = old_value | setvalue
                old_values[attr_name] = old_value

        if new_identifiers is not UNDEFINED:
            new_values["identifiers"] = new_identifiers
            old_values["identifiers"] = old.identifiers

        for attr_name, value in (
            ("configuration_url", configuration_url),
            ("disabled_by", disabled_by),
            ("entry_type", entry_type),
            ("manufacturer", manufacturer),
            ("model", model),
            ("name", name),
            ("name_by_user", name_by_user),
            ("area_id", area_id),
            ("suggested_area", suggested_area),
            ("sw_version", sw_version),
            ("hw_version", hw_version),
            ("via_device_id", via_device_id),
        ):
            if value is not UNDEFINED and value != getattr(old, attr_name):
                new_values[attr_name] = value
                old_values[attr_name] = getattr(old, attr_name)

        if old.is_new:
            new_values["is_new"] = False

        if not new_values:
            return old

        new = attr.evolve(old, **new_values)
        self._update_device(old, new)

        # If its only run time attributes (suggested_area)
        # that do not get saved we do not want to write
        # to disk or fire an event as we would end up
        # firing events for data we have nothing to compare
        # against since its never saved on disk
        if RUNTIME_ONLY_ATTRS.issuperset(new_values):
            return new

        self.async_schedule_save()

        data: dict[str, Any] = {
            "action": "create" if old.is_new else "update",
            "device_id": new.id,
        }
        if not old.is_new:
            data["changes"] = old_values

        self.hass.bus.async_fire(EVENT_DEVICE_REGISTRY_UPDATED, data)

        return new

    @callback
    def async_remove_device(self, device_id: str) -> None:
        """Remove a device from the device registry."""
        device = self.devices[device_id]
        self._remove_device(device)
        self._add_device(
            DeletedDeviceEntry(
                config_entries=device.config_entries,
                connections=device.connections,
                identifiers=device.identifiers,
                id=device.id,
                orphaned_timestamp=None,
            )
        )
        for other_device in list(self.devices.values()):
            if other_device.via_device_id == device_id:
                self.async_update_device(other_device.id, via_device_id=None)
        self.hass.bus.async_fire(
            EVENT_DEVICE_REGISTRY_UPDATED, {"action": "remove", "device_id": device_id}
        )
        self.async_schedule_save()

    async def async_load(self) -> None:
        """Load the device registry."""
        async_setup_cleanup(self.hass, self)

        data = await self._store.async_load()

        devices = OrderedDict()
        deleted_devices = OrderedDict()

        if data is not None:
            data = cast("dict[str, Any]", data)
            for device in data["devices"]:
                devices[device["id"]] = DeviceEntry(
                    area_id=device["area_id"],
                    config_entries=set(device["config_entries"]),
                    configuration_url=device["configuration_url"],
                    # type ignores (if tuple arg was cast): likely https://github.com/python/mypy/issues/8625
                    connections={tuple(conn) for conn in device["connections"]},  # type: ignore[misc]
                    disabled_by=DeviceEntryDisabler(device["disabled_by"])
                    if device["disabled_by"]
                    else None,
                    entry_type=DeviceEntryType(device["entry_type"])
                    if device["entry_type"]
                    else None,
                    id=device["id"],
                    identifiers={tuple(iden) for iden in device["identifiers"]},  # type: ignore[misc]
                    manufacturer=device["manufacturer"],
                    model=device["model"],
                    name_by_user=device["name_by_user"],
                    name=device["name"],
                    sw_version=device["sw_version"],
                    hw_version=device["hw_version"],
                    via_device_id=device["via_device_id"],
                )
            # Introduced in 0.111
            for device in data["deleted_devices"]:
                deleted_devices[device["id"]] = DeletedDeviceEntry(
                    config_entries=set(device["config_entries"]),
                    # type ignores (if tuple arg was cast): likely https://github.com/python/mypy/issues/8625
                    connections={tuple(conn) for conn in device["connections"]},  # type: ignore[misc]
                    identifiers={tuple(iden) for iden in device["identifiers"]},  # type: ignore[misc]
                    id=device["id"],
                    orphaned_timestamp=device["orphaned_timestamp"],
                )

        self.devices = devices
        self.deleted_devices = deleted_devices
        self._rebuild_index()

    @callback
    def async_schedule_save(self) -> None:
        """Schedule saving the device registry."""
        self._store.async_delay_save(self._data_to_save, SAVE_DELAY)

    @callback
    def _data_to_save(self) -> dict[str, list[dict[str, Any]]]:
        """Return data of device registry to store in a file."""
        data = {}

        data["devices"] = [
            {
                "config_entries": list(entry.config_entries),
                "connections": list(entry.connections),
                "identifiers": list(entry.identifiers),
                "manufacturer": entry.manufacturer,
                "model": entry.model,
                "name": entry.name,
                "sw_version": entry.sw_version,
                "hw_version": entry.hw_version,
                "entry_type": entry.entry_type,
                "id": entry.id,
                "via_device_id": entry.via_device_id,
                "area_id": entry.area_id,
                "name_by_user": entry.name_by_user,
                "disabled_by": entry.disabled_by,
                "configuration_url": entry.configuration_url,
            }
            for entry in self.devices.values()
        ]
        data["deleted_devices"] = [
            {
                "config_entries": list(entry.config_entries),
                "connections": list(entry.connections),
                "identifiers": list(entry.identifiers),
                "id": entry.id,
                "orphaned_timestamp": entry.orphaned_timestamp,
            }
            for entry in self.deleted_devices.values()
        ]

        return data

    @callback
    def async_clear_config_entry(self, config_entry_id: str) -> None:
        """Clear config entry from registry entries."""
        now_time = time.time()
        for device in list(self.devices.values()):
            self.async_update_device(device.id, remove_config_entry_id=config_entry_id)
        for deleted_device in list(self.deleted_devices.values()):
            config_entries = deleted_device.config_entries
            if config_entry_id not in config_entries:
                continue
            if config_entries == {config_entry_id}:
                # Add a time stamp when the deleted device became orphaned
                self.deleted_devices[deleted_device.id] = attr.evolve(
                    deleted_device, orphaned_timestamp=now_time, config_entries=set()
                )
            else:
                config_entries = config_entries - {config_entry_id}
                # No need to reindex here since we currently
                # do not have a lookup by config entry
                self.deleted_devices[deleted_device.id] = attr.evolve(
                    deleted_device, config_entries=config_entries
                )
            self.async_schedule_save()

    @callback
    def async_purge_expired_orphaned_devices(self) -> None:
        """Purge expired orphaned devices from the registry.

        We need to purge these periodically to avoid the database
        growing without bound.
        """
        now_time = time.time()
        for deleted_device in list(self.deleted_devices.values()):
            if deleted_device.orphaned_timestamp is None:
                continue

            if (
                deleted_device.orphaned_timestamp + ORPHANED_DEVICE_KEEP_SECONDS
                < now_time
            ):
                self._remove_device(deleted_device)

    @callback
    def async_clear_area_id(self, area_id: str) -> None:
        """Clear area id from registry entries."""
        for dev_id, device in self.devices.items():
            if area_id == device.area_id:
                self.async_update_device(dev_id, area_id=None)


@callback
def async_get(hass: HomeAssistant) -> DeviceRegistry:
    """Get device registry."""
    return cast(DeviceRegistry, hass.data[DATA_REGISTRY])


async def async_load(hass: HomeAssistant) -> None:
    """Load device registry."""
    assert DATA_REGISTRY not in hass.data
    hass.data[DATA_REGISTRY] = DeviceRegistry(hass)
    await hass.data[DATA_REGISTRY].async_load()


@bind_hass
async def async_get_registry(hass: HomeAssistant) -> DeviceRegistry:
    """Get device registry.

    This is deprecated and will be removed in the future. Use async_get instead.
    """
    return async_get(hass)


@callback
def async_entries_for_area(registry: DeviceRegistry, area_id: str) -> list[DeviceEntry]:
    """Return entries that match an area."""
    return [device for device in registry.devices.values() if device.area_id == area_id]


@callback
def async_entries_for_config_entry(
    registry: DeviceRegistry, config_entry_id: str
) -> list[DeviceEntry]:
    """Return entries that match a config entry."""
    return [
        device
        for device in registry.devices.values()
        if config_entry_id in device.config_entries
    ]


@callback
def async_config_entry_disabled_by_changed(
    registry: DeviceRegistry, config_entry: ConfigEntry
) -> None:
    """Handle a config entry being disabled or enabled.

    Disable devices in the registry that are associated with a config entry when
    the config entry is disabled, enable devices in the registry that are associated
    with a config entry when the config entry is enabled and the devices are marked
    DeviceEntryDisabler.CONFIG_ENTRY.
    Only disable a device if all associated config entries are disabled.
    """

    devices = async_entries_for_config_entry(registry, config_entry.entry_id)

    if not config_entry.disabled_by:
        for device in devices:
            if device.disabled_by is not DeviceEntryDisabler.CONFIG_ENTRY:
                continue
            registry.async_update_device(device.id, disabled_by=None)
        return

    enabled_config_entries = {
        entry.entry_id
        for entry in registry.hass.config_entries.async_entries()
        if not entry.disabled_by
    }

    for device in devices:
        if device.disabled:
            # Device already disabled, do not overwrite
            continue
        if len(device.config_entries) > 1 and device.config_entries.intersection(
            enabled_config_entries
        ):
            continue
        registry.async_update_device(
            device.id, disabled_by=DeviceEntryDisabler.CONFIG_ENTRY
        )


@callback
def async_cleanup(
    hass: HomeAssistant,
    dev_reg: DeviceRegistry,
    ent_reg: entity_registry.EntityRegistry,
) -> None:
    """Clean up device registry."""
    # Find all devices that are referenced by a config_entry.
    config_entry_ids = {entry.entry_id for entry in hass.config_entries.async_entries()}
    references_config_entries = {
        device.id
        for device in dev_reg.devices.values()
        for config_entry_id in device.config_entries
        if config_entry_id in config_entry_ids
    }

    # Find all devices that are referenced in the entity registry.
    references_entities = {entry.device_id for entry in ent_reg.entities.values()}

    orphan = set(dev_reg.devices) - references_entities - references_config_entries

    for dev_id in orphan:
        dev_reg.async_remove_device(dev_id)

    # Find all referenced config entries that no longer exist
    # This shouldn't happen but have not been able to track down the bug :(
    for device in list(dev_reg.devices.values()):
        for config_entry_id in device.config_entries:
            if config_entry_id not in config_entry_ids:
                dev_reg.async_update_device(
                    device.id, remove_config_entry_id=config_entry_id
                )

    # Periodic purge of orphaned devices to avoid the registry
    # growing without bounds when there are lots of deleted devices
    dev_reg.async_purge_expired_orphaned_devices()


@callback
def async_setup_cleanup(hass: HomeAssistant, dev_reg: DeviceRegistry) -> None:
    """Clean up device registry when entities removed."""
    from . import entity_registry  # pylint: disable=import-outside-toplevel

    async def cleanup() -> None:
        """Cleanup."""
        ent_reg = await entity_registry.async_get_registry(hass)
        async_cleanup(hass, dev_reg, ent_reg)

    debounced_cleanup = Debouncer(
        hass, _LOGGER, cooldown=CLEANUP_DELAY, immediate=False, function=cleanup
    )

    async def entity_registry_changed(event: Event) -> None:
        """Handle entity updated or removed dispatch."""
        await debounced_cleanup.async_call()

    @callback
    def entity_registry_changed_filter(event: Event) -> bool:
        """Handle entity updated or removed filter."""
        if (
            event.data["action"] == "update"
            and "device_id" not in event.data["changes"]
        ) or event.data["action"] == "create":
            return False

        return True

    if hass.is_running:
        hass.bus.async_listen(
            entity_registry.EVENT_ENTITY_REGISTRY_UPDATED,
            entity_registry_changed,
            event_filter=entity_registry_changed_filter,
        )
        return

    async def startup_clean(event: Event) -> None:
        """Clean up on startup."""
        hass.bus.async_listen(
            entity_registry.EVENT_ENTITY_REGISTRY_UPDATED,
            entity_registry_changed,
            event_filter=entity_registry_changed_filter,
        )
        await debounced_cleanup.async_call()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, startup_clean)


def _normalize_connections(connections: set[tuple[str, str]]) -> set[tuple[str, str]]:
    """Normalize connections to ensure we can match mac addresses."""
    return {
        (key, format_mac(value)) if key == CONNECTION_NETWORK_MAC else (key, value)
        for key, value in connections
    }


def _add_device_to_index(
    devices_index: _DeviceIndex,
    device: DeviceEntry | DeletedDeviceEntry,
) -> None:
    """Add a device to the index."""
    for identifier in device.identifiers:
        devices_index.identifiers[identifier] = device.id
    for connection in device.connections:
        devices_index.connections[connection] = device.id


def _remove_device_from_index(
    devices_index: _DeviceIndex,
    device: DeviceEntry | DeletedDeviceEntry,
) -> None:
    """Remove a device from the index."""
    for identifier in device.identifiers:
        if identifier in devices_index.identifiers:
            del devices_index.identifiers[identifier]
    for connection in device.connections:
        if connection in devices_index.connections:
            del devices_index.connections[connection]
