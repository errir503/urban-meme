"""YoLink DataUpdateCoordinator."""
from __future__ import annotations

from datetime import timedelta
import logging

import async_timeout
from yolink.device import YoLinkDevice
from yolink.exception import YoLinkAuthFailError, YoLinkClientError

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import ATTR_DEVICE_STATE, DOMAIN

_LOGGER = logging.getLogger(__name__)


class YoLinkCoordinator(DataUpdateCoordinator[dict]):
    """YoLink DataUpdateCoordinator."""

    def __init__(self, hass: HomeAssistant, device: YoLinkDevice) -> None:
        """Init YoLink DataUpdateCoordinator.

        fetch state every 30 minutes base on yolink device heartbeat interval
        data is None before the first successful update, but we need to use
        data at first update
        """
        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=timedelta(minutes=30)
        )
        self.device = device

    async def _async_update_data(self) -> dict:
        """Fetch device state."""
        try:
            async with async_timeout.timeout(10):
                device_state_resp = await self.device.fetch_state()
        except YoLinkAuthFailError as yl_auth_err:
            raise ConfigEntryAuthFailed from yl_auth_err
        except YoLinkClientError as yl_client_err:
            raise UpdateFailed from yl_client_err
        if ATTR_DEVICE_STATE in device_state_resp.data:
            return device_state_resp.data[ATTR_DEVICE_STATE]
        return {}
