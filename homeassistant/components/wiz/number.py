"""Support for WiZ effect speed numbers."""
from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Optional, cast

from pywizlight import wizlight

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import WizEntity
from .models import WizData


@dataclass
class WizNumberEntityDescriptionMixin:
    """Mixin to describe a WiZ number entity."""

    value_fn: Callable[[wizlight], int | None]
    set_value_fn: Callable[[wizlight, int], Coroutine[None, None, None]]
    required_feature: str


@dataclass
class WizNumberEntityDescription(
    NumberEntityDescription, WizNumberEntityDescriptionMixin
):
    """Class to describe a WiZ number entity."""


async def _async_set_speed(device: wizlight, speed: int) -> None:
    await device.set_speed(speed)


async def _async_set_ratio(device: wizlight, ratio: int) -> None:
    await device.set_ratio(ratio)


NUMBERS: tuple[WizNumberEntityDescription, ...] = (
    WizNumberEntityDescription(
        key="effect_speed",
        min_value=10,
        max_value=200,
        step=1,
        icon="mdi:speedometer",
        name="Effect Speed",
        value_fn=lambda device: cast(Optional[int], device.state.get_speed()),
        set_value_fn=_async_set_speed,
        required_feature="effect",
    ),
    WizNumberEntityDescription(
        key="dual_head_ratio",
        min_value=0,
        max_value=100,
        step=1,
        icon="mdi:floor-lamp-dual",
        name="Dual Head Ratio",
        value_fn=lambda device: cast(Optional[int], device.state.get_ratio()),
        set_value_fn=_async_set_ratio,
        required_feature="dual_head",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the wiz speed number."""
    wiz_data: WizData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        WizSpeedNumber(wiz_data, entry.title, description)
        for description in NUMBERS
        if getattr(wiz_data.bulb.bulbtype.features, description.required_feature)
    )


class WizSpeedNumber(WizEntity, NumberEntity):
    """Defines a WiZ speed number."""

    entity_description: WizNumberEntityDescription
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self, wiz_data: WizData, name: str, description: WizNumberEntityDescription
    ) -> None:
        """Initialize an WiZ device."""
        super().__init__(wiz_data, name)
        self.entity_description = description
        self._attr_unique_id = f"{self._device.mac}_{description.key}"
        self._attr_name = f"{name} {description.name}"
        self._async_update_attrs()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            super().available
            and self.entity_description.value_fn(self._device) is not None
        )

    @callback
    def _async_update_attrs(self) -> None:
        """Handle updating _attr values."""
        if (value := self.entity_description.value_fn(self._device)) is not None:
            self._attr_value = float(value)

    async def async_set_value(self, value: float) -> None:
        """Set the speed value."""
        await self.entity_description.set_value_fn(self._device, int(value))
        await self.coordinator.async_request_refresh()
