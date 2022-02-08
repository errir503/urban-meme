"""Representation of a toggleButton."""
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from . import ZWaveMeEntity
from .const import DOMAIN, ZWaveMePlatform

DEVICE_NAME = ZWaveMePlatform.BUTTON


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the number platform."""

    @callback
    def add_new_device(new_device):
        controller = hass.data[DOMAIN][config_entry.entry_id]
        button = ZWaveMeButton(controller, new_device)

        async_add_entities(
            [
                button,
            ]
        )

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass, f"ZWAVE_ME_NEW_{DEVICE_NAME.upper()}", add_new_device
        )
    )


class ZWaveMeButton(ZWaveMeEntity, ButtonEntity):
    """Representation of a ZWaveMe button."""

    def press(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        self.controller.zwave_api.send_command(self.device.id, "on")
