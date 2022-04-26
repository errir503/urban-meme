"""Support for Synology DSM binary sensors."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from synology_dsm.api.core.security import SynoCoreSecurity
from synology_dsm.api.core.upgrade import SynoCoreUpgrade
from synology_dsm.api.storage.storage import SynoStorage

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DISKS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import SynoApi
from .const import COORDINATOR_CENTRAL, DOMAIN, SYNO_API
from .entity import (
    SynologyDSMBaseEntity,
    SynologyDSMDeviceEntity,
    SynologyDSMEntityDescription,
)


@dataclass
class SynologyDSMBinarySensorEntityDescription(
    BinarySensorEntityDescription, SynologyDSMEntityDescription
):
    """Describes Synology DSM binary sensor entity."""


UPGRADE_BINARY_SENSORS: tuple[SynologyDSMBinarySensorEntityDescription, ...] = (
    SynologyDSMBinarySensorEntityDescription(
        # Deprecated, scheduled to be removed in 2022.6 (#68664)
        api_key=SynoCoreUpgrade.API_KEY,
        key="update_available",
        name="Update Available",
        entity_registry_enabled_default=False,
        device_class=BinarySensorDeviceClass.UPDATE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

SECURITY_BINARY_SENSORS: tuple[SynologyDSMBinarySensorEntityDescription, ...] = (
    SynologyDSMBinarySensorEntityDescription(
        api_key=SynoCoreSecurity.API_KEY,
        key="status",
        name="Security Status",
        device_class=BinarySensorDeviceClass.SAFETY,
    ),
)

STORAGE_DISK_BINARY_SENSORS: tuple[SynologyDSMBinarySensorEntityDescription, ...] = (
    SynologyDSMBinarySensorEntityDescription(
        api_key=SynoStorage.API_KEY,
        key="disk_exceed_bad_sector_thr",
        name="Exceeded Max Bad Sectors",
        device_class=BinarySensorDeviceClass.SAFETY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SynologyDSMBinarySensorEntityDescription(
        api_key=SynoStorage.API_KEY,
        key="disk_below_remain_life_thr",
        name="Below Min Remaining Life",
        device_class=BinarySensorDeviceClass.SAFETY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Synology NAS binary sensor."""

    data = hass.data[DOMAIN][entry.unique_id]
    api: SynoApi = data[SYNO_API]
    coordinator = data[COORDINATOR_CENTRAL]

    entities: list[
        SynoDSMSecurityBinarySensor
        | SynoDSMUpgradeBinarySensor
        | SynoDSMStorageBinarySensor
    ] = [
        SynoDSMSecurityBinarySensor(api, coordinator, description)
        for description in SECURITY_BINARY_SENSORS
    ]

    entities.extend(
        [
            SynoDSMUpgradeBinarySensor(api, coordinator, description)
            for description in UPGRADE_BINARY_SENSORS
        ]
    )

    # Handle all disks
    if api.storage.disks_ids:
        entities.extend(
            [
                SynoDSMStorageBinarySensor(api, coordinator, description, disk)
                for disk in entry.data.get(CONF_DISKS, api.storage.disks_ids)
                for description in STORAGE_DISK_BINARY_SENSORS
            ]
        )

    async_add_entities(entities)


class SynoDSMBinarySensor(SynologyDSMBaseEntity, BinarySensorEntity):
    """Mixin for binary sensor specific attributes."""

    entity_description: SynologyDSMBinarySensorEntityDescription

    def __init__(
        self,
        api: SynoApi,
        coordinator: DataUpdateCoordinator[dict[str, dict[str, Any]]],
        description: SynologyDSMBinarySensorEntityDescription,
    ) -> None:
        """Initialize the Synology DSM binary_sensor entity."""
        super().__init__(api, coordinator, description)


class SynoDSMSecurityBinarySensor(SynoDSMBinarySensor):
    """Representation a Synology Security binary sensor."""

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return getattr(self._api.security, self.entity_description.key) != "safe"  # type: ignore[no-any-return]

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return bool(self._api.security)

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return security checks details."""
        return self._api.security.status_by_check  # type: ignore[no-any-return]


class SynoDSMStorageBinarySensor(SynologyDSMDeviceEntity, SynoDSMBinarySensor):
    """Representation a Synology Storage binary sensor."""

    entity_description: SynologyDSMBinarySensorEntityDescription

    def __init__(
        self,
        api: SynoApi,
        coordinator: DataUpdateCoordinator[dict[str, dict[str, Any]]],
        description: SynologyDSMBinarySensorEntityDescription,
        device_id: str | None = None,
    ) -> None:
        """Initialize the Synology DSM storage binary_sensor entity."""
        super().__init__(api, coordinator, description, device_id)

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return bool(
            getattr(self._api.storage, self.entity_description.key)(self._device_id)
        )


class SynoDSMUpgradeBinarySensor(SynoDSMBinarySensor):
    """Representation a Synology Upgrade binary sensor."""

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return bool(getattr(self._api.upgrade, self.entity_description.key))

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return bool(self._api.upgrade)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return firmware details."""
        return {
            "installed_version": self._api.information.version_string,
            "latest_available_version": self._api.upgrade.available_version,
        }
