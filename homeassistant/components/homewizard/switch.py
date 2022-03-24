"""Creates Homewizard Energy switch entities."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HWEnergyDeviceUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches."""
    coordinator: HWEnergyDeviceUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    if coordinator.api.state:
        async_add_entities(
            [
                HWEnergyMainSwitchEntity(coordinator, entry),
                HWEnergySwitchLockEntity(coordinator, entry),
            ]
        )


class HWEnergySwitchEntity(
    CoordinatorEntity[HWEnergyDeviceUpdateCoordinator], SwitchEntity
):
    """Representation switchable entity."""

    def __init__(
        self,
        coordinator: HWEnergyDeviceUpdateCoordinator,
        entry: ConfigEntry,
        key: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_device_info = {
            "name": entry.title,
            "manufacturer": "HomeWizard",
            "sw_version": coordinator.data["device"].firmware_version,
            "model": coordinator.data["device"].product_type,
            "identifiers": {(DOMAIN, coordinator.data["device"].serial)},
        }


class HWEnergyMainSwitchEntity(HWEnergySwitchEntity):
    """Representation of the main power switch."""

    _attr_device_class = SwitchDeviceClass.OUTLET

    def __init__(
        self, coordinator: HWEnergyDeviceUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, entry, "power_on")

        # Config attributes
        self._attr_name = f"{entry.title} Switch"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self.coordinator.api.state.set(power_on=True)
        await self.coordinator.async_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.coordinator.api.state.set(power_on=False)
        await self.coordinator.async_refresh()

    @property
    def available(self) -> bool:
        """
        Return availability of power_on.

        This switch becomes unavailable when switch_lock is enabled.
        """
        return super().available and not self.coordinator.api.state.switch_lock

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return bool(self.coordinator.api.state.power_on)


class HWEnergySwitchLockEntity(HWEnergySwitchEntity):
    """
    Representation of the switch-lock configuration.

    Switch-lock is a feature that forces the relay in 'on' state.
    It disables any method that can turn of the relay.
    """

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: HWEnergyDeviceUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, entry, "switch_lock")

        # Config attributes
        self._attr_name = f"{entry.title} Switch Lock"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn switch-lock on."""
        await self.coordinator.api.state.set(switch_lock=True)
        await self.coordinator.async_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn switch-lock off."""
        await self.coordinator.api.state.set(switch_lock=False)
        await self.coordinator.async_refresh()

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return bool(self.coordinator.api.state.switch_lock)
