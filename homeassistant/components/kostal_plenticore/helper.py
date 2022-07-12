"""Code to handle the Plenticore API."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import Any

from aiohttp.client_exceptions import ClientError
from kostal.plenticore import (
    PlenticoreApiClient,
    PlenticoreApiException,
    PlenticoreAuthenticationException,
)

from homeassistant.const import CONF_HOST, CONF_PASSWORD, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class Plenticore:
    """Manages the Plenticore API."""

    def __init__(self, hass, config_entry):
        """Create a new plenticore manager instance."""
        self.hass = hass
        self.config_entry = config_entry

        self._client = None
        self._shutdown_remove_listener = None

        self.device_info = {}

    @property
    def host(self) -> str:
        """Return the host of the Plenticore inverter."""
        return self.config_entry.data[CONF_HOST]

    @property
    def client(self) -> PlenticoreApiClient:
        """Return the Plenticore API client."""
        return self._client

    async def async_setup(self) -> bool:
        """Set up Plenticore API client."""
        self._client = PlenticoreApiClient(
            async_get_clientsession(self.hass), host=self.host
        )
        try:
            await self._client.login(self.config_entry.data[CONF_PASSWORD])
        except PlenticoreAuthenticationException as err:
            _LOGGER.error(
                "Authentication exception connecting to %s: %s", self.host, err
            )
            return False
        except (ClientError, asyncio.TimeoutError) as err:
            _LOGGER.error("Error connecting to %s", self.host)
            raise ConfigEntryNotReady from err
        else:
            _LOGGER.debug("Log-in successfully to %s", self.host)

        self._shutdown_remove_listener = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, self._async_shutdown
        )

        # get some device meta data
        settings = await self._client.get_setting_values(
            {
                "devices:local": [
                    "Properties:SerialNo",
                    "Branding:ProductName1",
                    "Branding:ProductName2",
                    "Properties:VersionIOC",
                    "Properties:VersionMC",
                ],
                "scb:network": ["Hostname"],
            }
        )

        device_local = settings["devices:local"]
        prod1 = device_local["Branding:ProductName1"]
        prod2 = device_local["Branding:ProductName2"]

        self.device_info = DeviceInfo(
            configuration_url=f"http://{self.host}",
            identifiers={(DOMAIN, device_local["Properties:SerialNo"])},
            manufacturer="Kostal",
            model=f"{prod1} {prod2}",
            name=settings["scb:network"]["Hostname"],
            sw_version=f'IOC: {device_local["Properties:VersionIOC"]}'
            + f' MC: {device_local["Properties:VersionMC"]}',
        )

        return True

    async def _async_shutdown(self, event):
        """Call from Homeassistant shutdown event."""
        # unset remove listener otherwise calling it would raise an exception
        self._shutdown_remove_listener = None
        await self.async_unload()

    async def async_unload(self) -> None:
        """Unload the Plenticore API client."""
        if self._shutdown_remove_listener:
            self._shutdown_remove_listener()

        await self._client.logout()
        self._client = None
        _LOGGER.debug("Logged out from %s", self.host)


class DataUpdateCoordinatorMixin:
    """Base implementation for read and write data."""

    _plenticore: Plenticore
    name: str

    async def async_read_data(
        self, module_id: str, data_id: str
    ) -> dict[str, dict[str, str]] | None:
        """Read data from Plenticore."""
        if (client := self._plenticore.client) is None:
            return None

        try:
            return await client.get_setting_values(module_id, data_id)
        except PlenticoreApiException:
            return None

    async def async_write_data(self, module_id: str, value: dict[str, str]) -> bool:
        """Write settings back to Plenticore."""
        if (client := self._plenticore.client) is None:
            return False

        _LOGGER.debug(
            "Setting value for %s in module %s to %s", self.name, module_id, value
        )

        try:
            await client.set_setting_values(module_id, value)
        except PlenticoreApiException:
            return False
        else:
            return True


class PlenticoreUpdateCoordinator(DataUpdateCoordinator):
    """Base implementation of DataUpdateCoordinator for Plenticore data."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        name: str,
        update_inverval: timedelta,
        plenticore: Plenticore,
    ) -> None:
        """Create a new update coordinator for plenticore data."""
        super().__init__(
            hass=hass,
            logger=logger,
            name=name,
            update_interval=update_inverval,
        )
        # data ids to poll
        self._fetch: dict[str, list[str]] = defaultdict(list)
        self._plenticore = plenticore

    def start_fetch_data(self, module_id: str, data_id: str) -> None:
        """Start fetching the given data (module-id and data-id)."""
        self._fetch[module_id].append(data_id)

        # Force an update of all data. Multiple refresh calls
        # are ignored by the debouncer.
        async def force_refresh(event_time: datetime) -> None:
            await self.async_request_refresh()

        async_call_later(self.hass, 2, force_refresh)

    def stop_fetch_data(self, module_id: str, data_id: str) -> None:
        """Stop fetching the given data (module-id and data-id)."""
        self._fetch[module_id].remove(data_id)


class ProcessDataUpdateCoordinator(PlenticoreUpdateCoordinator):
    """Implementation of PlenticoreUpdateCoordinator for process data."""

    async def _async_update_data(self) -> dict[str, dict[str, str]]:
        client = self._plenticore.client

        if not self._fetch or client is None:
            return {}

        _LOGGER.debug("Fetching %s for %s", self.name, self._fetch)

        fetched_data = await client.get_process_data_values(self._fetch)
        return {
            module_id: {
                process_data.id: process_data.value
                for process_data in fetched_data[module_id]
            }
            for module_id in fetched_data
        }


class SettingDataUpdateCoordinator(
    PlenticoreUpdateCoordinator, DataUpdateCoordinatorMixin
):
    """Implementation of PlenticoreUpdateCoordinator for settings data."""

    async def _async_update_data(self) -> dict[str, dict[str, str]]:
        client = self._plenticore.client

        if not self._fetch or client is None:
            return {}

        _LOGGER.debug("Fetching %s for %s", self.name, self._fetch)

        fetched_data = await client.get_setting_values(self._fetch)
        return fetched_data


class PlenticoreSelectUpdateCoordinator(DataUpdateCoordinator):
    """Base implementation of DataUpdateCoordinator for Plenticore data."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        name: str,
        update_inverval: timedelta,
        plenticore: Plenticore,
    ) -> None:
        """Create a new update coordinator for plenticore data."""
        super().__init__(
            hass=hass,
            logger=logger,
            name=name,
            update_interval=update_inverval,
        )
        # data ids to poll
        self._fetch: dict[str, list[str]] = defaultdict(list)
        self._plenticore = plenticore

    def start_fetch_data(self, module_id: str, data_id: str, all_options: str) -> None:
        """Start fetching the given data (module-id and entry-id)."""
        self._fetch[module_id].append(data_id)
        self._fetch[module_id].append(all_options)

        # Force an update of all data. Multiple refresh calls
        # are ignored by the debouncer.
        async def force_refresh(event_time: datetime) -> None:
            await self.async_request_refresh()

        async_call_later(self.hass, 2, force_refresh)

    def stop_fetch_data(self, module_id: str, data_id: str, all_options: str) -> None:
        """Stop fetching the given data (module-id and entry-id)."""
        self._fetch[module_id].remove(all_options)
        self._fetch[module_id].remove(data_id)


class SelectDataUpdateCoordinator(
    PlenticoreSelectUpdateCoordinator, DataUpdateCoordinatorMixin
):
    """Implementation of PlenticoreUpdateCoordinator for select data."""

    async def _async_update_data(self) -> dict[str, dict[str, str]]:
        if self._plenticore.client is None:
            return {}

        _LOGGER.debug("Fetching select %s for %s", self.name, self._fetch)

        fetched_data = await self._async_get_current_option(self._fetch)

        return fetched_data

    async def _async_get_current_option(
        self,
        module_id: dict[str, list[str]],
    ) -> dict[str, dict[str, str]]:
        """Get current option."""
        for mid, pids in module_id.items():
            all_options = pids[1]
            for all_option in all_options:
                if all_option == "None" or not (
                    val := await self.async_read_data(mid, all_option)
                ):
                    continue
                for option in val.values():
                    if option[all_option] == "1":
                        fetched = {mid: {pids[0]: all_option}}
                        return fetched

            return {mid: {pids[0]: "None"}}
        return {}


class PlenticoreDataFormatter:
    """Provides method to format values of process or settings data."""

    INVERTER_STATES = {
        0: "Off",
        1: "Init",
        2: "IsoMEas",
        3: "GridCheck",
        4: "StartUp",
        6: "FeedIn",
        7: "Throttled",
        8: "ExtSwitchOff",
        9: "Update",
        10: "Standby",
        11: "GridSync",
        12: "GridPreCheck",
        13: "GridSwitchOff",
        14: "Overheating",
        15: "Shutdown",
        16: "ImproperDcVoltage",
        17: "ESB",
    }

    EM_STATES = {
        0: "Idle",
        1: "n/a",
        2: "Emergency Battery Charge",
        4: "n/a",
        8: "Winter Mode Step 1",
        16: "Winter Mode Step 2",
    }

    @classmethod
    def get_method(cls, name: str) -> Callable[[Any], Any]:
        """Return a callable formatter of the given name."""
        return getattr(cls, name)

    @staticmethod
    def format_round(state: str) -> int | str:
        """Return the given state value as rounded integer."""
        try:
            return round(float(state))
        except (TypeError, ValueError):
            return state

    @staticmethod
    def format_round_back(value: float) -> str:
        """Return a rounded integer value from a float."""
        try:
            if isinstance(value, float) and value.is_integer():
                int_value = int(value)
            elif isinstance(value, int):
                int_value = value
            else:
                int_value = round(value)

            return str(int_value)
        except (TypeError, ValueError):
            return ""

    @staticmethod
    def format_float(state: str) -> float | str:
        """Return the given state value as float rounded to three decimal places."""
        try:
            return round(float(state), 3)
        except (TypeError, ValueError):
            return state

    @staticmethod
    def format_energy(state: str) -> float | str:
        """Return the given state value as energy value, scaled to kWh."""
        try:
            return round(float(state) / 1000, 1)
        except (TypeError, ValueError):
            return state

    @staticmethod
    def format_inverter_state(state: str) -> str | None:
        """Return a readable string of the inverter state."""
        try:
            value = int(state)
        except (TypeError, ValueError):
            return state

        return PlenticoreDataFormatter.INVERTER_STATES.get(value)

    @staticmethod
    def format_em_manager_state(state: str) -> str | None:
        """Return a readable state of the energy manager."""
        try:
            value = int(state)
        except (TypeError, ValueError):
            return state

        return PlenticoreDataFormatter.EM_STATES.get(value)
