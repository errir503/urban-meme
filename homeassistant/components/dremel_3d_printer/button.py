"""Support for Dremel 3D Printer buttons."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from dremel3dpy import Dremel3DPrinter

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import Dremel3DPrinterEntity


@dataclass
class Dremel3DPrinterButtonEntityMixin:
    """Mixin for required keys."""

    press_fn: Callable[[Dremel3DPrinter], None]


@dataclass
class Dremel3DPrinterButtonEntityDescription(
    ButtonEntityDescription, Dremel3DPrinterButtonEntityMixin
):
    """Describes a Dremel 3D Printer button entity."""


BUTTON_TYPES: tuple[Dremel3DPrinterButtonEntityDescription, ...] = (
    Dremel3DPrinterButtonEntityDescription(
        key="cancel_job",
        translation_key="cancel_job",
        press_fn=lambda api: api.stop_print(),
    ),
    Dremel3DPrinterButtonEntityDescription(
        key="pause_job",
        translation_key="pause_job",
        press_fn=lambda api: api.pause_print(),
    ),
    Dremel3DPrinterButtonEntityDescription(
        key="resume_job",
        translation_key="resume_job",
        press_fn=lambda api: api.resume_print(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dremel 3D Printer control buttons."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        Dremel3DPrinterButtonEntity(coordinator, description)
        for description in BUTTON_TYPES
    )


class Dremel3DPrinterButtonEntity(Dremel3DPrinterEntity, ButtonEntity):
    """Represent a Dremel 3D Printer button."""

    entity_description: Dremel3DPrinterButtonEntityDescription

    def press(self) -> None:
        """Handle the button press."""
        # api does not care about the current state
        try:
            self.entity_description.press_fn(self._api)
        except RuntimeError as ex:
            raise HomeAssistantError(
                "An error occurred while submitting command"
            ) from ex
