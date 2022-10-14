"""Data update coordinator for the Jellyfin integration."""
from __future__ import annotations

from abc import abstractmethod
from datetime import timedelta
from typing import Any, TypeVar, Union

from jellyfin_apiclient_python import JellyfinClient

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, LOGGER

JellyfinDataT = TypeVar(
    "JellyfinDataT",
    bound=Union[
        dict[str, dict[str, Any]],
        dict[str, Any],
    ],
)


class JellyfinDataUpdateCoordinator(DataUpdateCoordinator[JellyfinDataT]):
    """Data update coordinator for the Jellyfin integration."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: JellyfinClient,
        system_info: dict[str, Any],
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass=hass,
            logger=LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )
        self.api_client: JellyfinClient = api_client
        self.server_id: str = system_info["Id"]
        self.server_name: str = system_info["Name"]
        self.server_version: str | None = system_info.get("Version")

    async def _async_update_data(self) -> JellyfinDataT:
        """Get the latest data from Jellyfin."""
        return await self._fetch_data()

    @abstractmethod
    async def _fetch_data(self) -> JellyfinDataT:
        """Fetch the actual data."""
        raise NotImplementedError


class SessionsDataUpdateCoordinator(
    JellyfinDataUpdateCoordinator[dict[str, dict[str, Any]]]
):
    """Sessions update coordinator for Jellyfin."""

    async def _fetch_data(self) -> dict:
        """Fetch the data."""
        sessions = await self.hass.async_add_executor_job(
            self.api_client.jellyfin.sessions
        )

        return {session["Id"]: session for session in sessions}
