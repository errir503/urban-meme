"""Support for Ubiquiti's UniFi Protect NVR."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pyunifiprotect.data.base import ProtectAdoptableDeviceModel

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .data import ProtectData
from .entity import ProtectDeviceEntity, async_all_device_entities
from .models import ProtectSetableKeysMixin, T


@dataclass
class ProtectButtonEntityDescription(
    ProtectSetableKeysMixin[T], ButtonEntityDescription
):
    """Describes UniFi Protect Button entity."""

    ufp_press: str | None = None


DEVICE_CLASS_CHIME_BUTTON: Final = "unifiprotect__chime_button"


ALL_DEVICE_BUTTONS: tuple[ProtectButtonEntityDescription, ...] = (
    ProtectButtonEntityDescription(
        key="reboot",
        entity_registry_enabled_default=False,
        device_class=ButtonDeviceClass.RESTART,
        name="Reboot Device",
        ufp_press="reboot",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Discover devices on a UniFi Protect NVR."""
    data: ProtectData = hass.data[DOMAIN][entry.entry_id]

    entities: list[ProtectDeviceEntity] = async_all_device_entities(
        data, ProtectButton, all_descs=ALL_DEVICE_BUTTONS
    )

    async_add_entities(entities)


class ProtectButton(ProtectDeviceEntity, ButtonEntity):
    """A Ubiquiti UniFi Protect Reboot button."""

    entity_description: ProtectButtonEntityDescription

    def __init__(
        self,
        data: ProtectData,
        device: ProtectAdoptableDeviceModel,
        description: ProtectButtonEntityDescription,
    ) -> None:
        """Initialize an UniFi camera."""
        super().__init__(data, device, description)
        self._attr_name = f"{self.device.name} {self.entity_description.name}"

    async def async_press(self) -> None:
        """Press the button."""

        if self.entity_description.ufp_press is not None:
            await getattr(self.device, self.entity_description.ufp_press)()
