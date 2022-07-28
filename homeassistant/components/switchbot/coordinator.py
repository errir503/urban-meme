"""Provides the switchbot DataUpdateCoordinator."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

from bleak.backends.device import BLEDevice
import switchbot
from switchbot import parse_advertisement_data

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.passive_update_coordinator import (
    PassiveBluetoothDataUpdateCoordinator,
)
from homeassistant.core import HomeAssistant, callback

_LOGGER = logging.getLogger(__name__)


def flatten_sensors_data(sensor):
    """Deconstruct SwitchBot library temp object C/Fº readings from dictionary."""
    if "temp" in sensor["data"]:
        sensor["data"]["temperature"] = sensor["data"]["temp"]["c"]

    return sensor


class SwitchbotDataUpdateCoordinator(PassiveBluetoothDataUpdateCoordinator):
    """Class to manage fetching switchbot data."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        ble_device: BLEDevice,
        device: switchbot.SwitchbotDevice,
    ) -> None:
        """Initialize global switchbot data updater."""
        super().__init__(hass, logger, ble_device.address)
        self.ble_device = ble_device
        self.device = device
        self.data: dict[str, Any] = {}
        self._ready_event = asyncio.Event()

    @callback
    def _async_handle_bluetooth_event(
        self,
        service_info: bluetooth.BluetoothServiceInfo,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Handle a Bluetooth event."""
        super()._async_handle_bluetooth_event(service_info, change)
        discovery_info_bleak = cast(bluetooth.BluetoothServiceInfoBleak, service_info)
        if adv := parse_advertisement_data(
            discovery_info_bleak.device, discovery_info_bleak.advertisement
        ):
            self.data = flatten_sensors_data(adv.data)
            if "modelName" in self.data:
                self._ready_event.set()
            _LOGGER.debug("%s: Switchbot data: %s", self.ble_device.address, self.data)
            self.device.update_from_advertisement(adv)
        self.async_update_listeners()

    async def async_wait_ready(self) -> bool:
        """Wait for the device to be ready."""
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=55)
        except asyncio.TimeoutError:
            return False
        return True
