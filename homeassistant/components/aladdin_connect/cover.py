"""Platform for the Aladdin Connect cover component."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from AIOAladdinConnect import AladdinConnectClient, session_manager

from homeassistant.components.cover import CoverDeviceClass, CoverEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_CLOSED, STATE_CLOSING, STATE_OPENING
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, STATES_MAP, SUPPORTED_FEATURES
from .model import DoorDevice

SCAN_INTERVAL = timedelta(seconds=300)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Aladdin Connect platform."""
    acc: AladdinConnectClient = hass.data[DOMAIN][config_entry.entry_id]
    doors = await acc.get_doors()
    if doors is None:
        raise PlatformNotReady("Error from Aladdin Connect getting doors")
    async_add_entities(
        (AladdinDevice(acc, door, config_entry) for door in doors),
    )


class AladdinDevice(CoverEntity):
    """Representation of Aladdin Connect cover."""

    _attr_device_class = CoverDeviceClass.GARAGE
    _attr_supported_features = SUPPORTED_FEATURES

    def __init__(
        self, acc: AladdinConnectClient, device: DoorDevice, entry: ConfigEntry
    ) -> None:
        """Initialize the Aladdin Connect cover."""
        self._acc = acc
        self._entry_id = entry.entry_id
        self._device_id = device["device_id"]
        self._number = device["door_number"]
        self._name = device["name"]
        self._serial = device["serial"]
        self._model = device["model"]

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{self._device_id}-{self._number}")},
            name=self._name,
            manufacturer="Overhead Door",
            model=self._model,
        )
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{self._device_id}-{self._number}"

    async def async_added_to_hass(self) -> None:
        """Connect Aladdin Connect to the cloud."""

        self._acc.register_callback(
            self.async_write_ha_state, self._serial, self._number
        )
        await self._acc.get_doors(self._serial)

    async def async_will_remove_from_hass(self) -> None:
        """Close Aladdin Connect before removing."""
        self._acc.unregister_callback(self._serial, self._number)
        await self._acc.close()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Issue close command to cover."""
        await self._acc.close_door(self._device_id, self._number)

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Issue open command to cover."""
        await self._acc.open_door(self._device_id, self._number)

    async def async_update(self) -> None:
        """Update status of cover."""
        try:
            await self._acc.get_doors(self._serial)
            self._attr_available = True

        except session_manager.ConnectionError:
            self._attr_available = False

        except session_manager.InvalidPasswordError:
            self._attr_available = False
            await self.hass.async_create_task(
                self.hass.config_entries.async_reload(self._entry_id)
            )

    @property
    def is_closed(self) -> bool | None:
        """Update is closed attribute."""
        value = STATES_MAP.get(self._acc.get_door_status(self._device_id, self._number))
        if value is None:
            return None
        return value == STATE_CLOSED

    @property
    def is_closing(self) -> bool:
        """Update is closing attribute."""
        return (
            STATES_MAP.get(self._acc.get_door_status(self._device_id, self._number))
            == STATE_CLOSING
        )

    @property
    def is_opening(self) -> bool:
        """Update is opening attribute."""
        return (
            STATES_MAP.get(self._acc.get_door_status(self._device_id, self._number))
            == STATE_OPENING
        )
