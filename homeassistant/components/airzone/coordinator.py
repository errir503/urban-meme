"""The Airzone integration."""
from __future__ import annotations

from datetime import timedelta
import logging

from aioairzone.exceptions import AirzoneError
from aioairzone.localapi import AirzoneLocalApi
import async_timeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import AIOAIRZONE_DEVICE_TIMEOUT_SEC, DOMAIN

SCAN_INTERVAL = timedelta(seconds=60)

_LOGGER = logging.getLogger(__name__)


class AirzoneUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Airzone device."""

    def __init__(self, hass: HomeAssistant, airzone: AirzoneLocalApi) -> None:
        """Initialize."""
        self.airzone = airzone

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self):
        """Update data via library."""
        async with async_timeout.timeout(AIOAIRZONE_DEVICE_TIMEOUT_SEC):
            try:
                await self.airzone.update()
            except AirzoneError as error:
                raise UpdateFailed(error) from error
            return self.airzone.data()
