"""Coordinator for FYTA integration."""

from datetime import datetime, timedelta
import logging
from typing import Any

from fyta_cli.fyta_connector import FytaConnector
from fyta_cli.fyta_exceptions import (
    FytaAuthentificationError,
    FytaConnectionError,
    FytaPasswordError,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


class FytaCoordinator(DataUpdateCoordinator[dict[int, dict[str, Any]]]):
    """Fyta custom coordinator."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, fyta: FytaConnector) -> None:
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="FYTA Coordinator",
            update_interval=timedelta(seconds=60),
        )
        self.fyta = fyta

    async def _async_update_data(
        self,
    ) -> dict[int, dict[str, Any]]:
        """Fetch data from API endpoint."""

        if self.fyta.expiration is None or self.fyta.expiration < datetime.now():
            await self.renew_authentication()

        return await self.fyta.update_all_plants()

    async def renew_authentication(self) -> None:
        """Renew access token for FYTA API."""

        try:
            await self.fyta.login()
        except FytaConnectionError as ex:
            raise ConfigEntryNotReady from ex
        except (FytaAuthentificationError, FytaPasswordError) as ex:
            raise ConfigEntryError from ex
