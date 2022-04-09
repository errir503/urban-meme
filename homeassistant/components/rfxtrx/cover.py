"""Support for RFXtrx covers."""
from __future__ import annotations

import logging

import RFXtrx as rfxtrxmod

from homeassistant.components.cover import CoverEntity, CoverEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OPEN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DeviceTuple, RfxtrxCommandEntity, async_setup_platform_entry
from .const import (
    COMMAND_OFF_LIST,
    COMMAND_ON_LIST,
    CONF_VENETIAN_BLIND_MODE,
    CONST_VENETIAN_BLIND_MODE_EU,
    CONST_VENETIAN_BLIND_MODE_US,
)

_LOGGER = logging.getLogger(__name__)


def supported(event: rfxtrxmod.RFXtrxEvent):
    """Return whether an event supports cover."""
    return event.device.known_to_be_rollershutter


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up config entry."""

    def _constructor(
        event: rfxtrxmod.RFXtrxEvent,
        auto: rfxtrxmod.RFXtrxEvent | None,
        device_id: DeviceTuple,
        entity_info: dict,
    ):
        return [
            RfxtrxCover(
                event.device,
                device_id,
                venetian_blind_mode=entity_info.get(CONF_VENETIAN_BLIND_MODE),
                event=event if auto else None,
            )
        ]

    await async_setup_platform_entry(
        hass, config_entry, async_add_entities, supported, _constructor
    )


class RfxtrxCover(RfxtrxCommandEntity, CoverEntity):
    """Representation of a RFXtrx cover."""

    _device: rfxtrxmod.RollerTrolDevice | rfxtrxmod.RfyDevice | rfxtrxmod.LightingDevice

    def __init__(
        self,
        device: rfxtrxmod.RFXtrxDevice,
        device_id: DeviceTuple,
        event: rfxtrxmod.RFXtrxEvent = None,
        venetian_blind_mode: bool | None = None,
    ) -> None:
        """Initialize the RFXtrx cover device."""
        super().__init__(device, device_id, event)
        self._venetian_blind_mode = venetian_blind_mode

    async def async_added_to_hass(self):
        """Restore device state."""
        await super().async_added_to_hass()

        if self._event is None:
            old_state = await self.async_get_last_state()
            if old_state is not None:
                self._state = old_state.state == STATE_OPEN

    @property
    def supported_features(self):
        """Flag supported features."""
        supported_features = (
            CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        )

        if self._venetian_blind_mode in (
            CONST_VENETIAN_BLIND_MODE_US,
            CONST_VENETIAN_BLIND_MODE_EU,
        ):
            supported_features |= (
                CoverEntityFeature.OPEN_TILT
                | CoverEntityFeature.CLOSE_TILT
                | CoverEntityFeature.STOP_TILT
            )

        return supported_features

    @property
    def is_closed(self):
        """Return if the cover is closed."""
        return not self._state

    async def async_open_cover(self, **kwargs):
        """Move the cover up."""
        if self._venetian_blind_mode == CONST_VENETIAN_BLIND_MODE_US:
            await self._async_send(self._device.send_up05sec)
        elif self._venetian_blind_mode == CONST_VENETIAN_BLIND_MODE_EU:
            await self._async_send(self._device.send_up2sec)
        else:
            await self._async_send(self._device.send_open)
        self._state = True
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs):
        """Move the cover down."""
        if self._venetian_blind_mode == CONST_VENETIAN_BLIND_MODE_US:
            await self._async_send(self._device.send_down05sec)
        elif self._venetian_blind_mode == CONST_VENETIAN_BLIND_MODE_EU:
            await self._async_send(self._device.send_down2sec)
        else:
            await self._async_send(self._device.send_close)
        self._state = False
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs):
        """Stop the cover."""
        await self._async_send(self._device.send_stop)
        self._state = True
        self.async_write_ha_state()

    async def async_open_cover_tilt(self, **kwargs):
        """Tilt the cover up."""
        if self._venetian_blind_mode == CONST_VENETIAN_BLIND_MODE_US:
            await self._async_send(self._device.send_up2sec)
        elif self._venetian_blind_mode == CONST_VENETIAN_BLIND_MODE_EU:
            await self._async_send(self._device.send_up05sec)

    async def async_close_cover_tilt(self, **kwargs):
        """Tilt the cover down."""
        if self._venetian_blind_mode == CONST_VENETIAN_BLIND_MODE_US:
            await self._async_send(self._device.send_down2sec)
        elif self._venetian_blind_mode == CONST_VENETIAN_BLIND_MODE_EU:
            await self._async_send(self._device.send_down05sec)

    async def async_stop_cover_tilt(self, **kwargs):
        """Stop the cover tilt."""
        await self._async_send(self._device.send_stop)
        self._state = True
        self.async_write_ha_state()

    def _apply_event(self, event: rfxtrxmod.RFXtrxEvent):
        """Apply command from rfxtrx."""
        assert isinstance(event, rfxtrxmod.ControlEvent)
        super()._apply_event(event)
        if event.values["Command"] in COMMAND_ON_LIST:
            self._state = True
        elif event.values["Command"] in COMMAND_OFF_LIST:
            self._state = False

    @callback
    def _handle_event(self, event: rfxtrxmod.RFXtrxEvent, device_id: DeviceTuple):
        """Check if event applies to me and update."""
        if device_id != self._device_id:
            return

        self._apply_event(event)

        self.async_write_ha_state()
