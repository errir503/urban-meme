"""The NextDNS component."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from aiohttp.client_exceptions import ClientConnectorError
from async_timeout import timeout
from nextdns import (
    AnalyticsDnssec,
    AnalyticsEncryption,
    AnalyticsIpVersions,
    AnalyticsProtocols,
    AnalyticsStatus,
    ApiError,
    InvalidApiKeyError,
    NextDns,
)
from nextdns.model import NextDnsData

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ATTR_DNSSEC,
    ATTR_ENCRYPTION,
    ATTR_IP_VERSIONS,
    ATTR_PROTOCOLS,
    ATTR_STATUS,
    CONF_PROFILE_ID,
    DOMAIN,
    UPDATE_INTERVAL_ANALYTICS,
)


class NextDnsUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching NextDNS data API."""

    def __init__(
        self,
        hass: HomeAssistant,
        nextdns: NextDns,
        profile_id: str,
        update_interval: timedelta,
    ) -> None:
        """Initialize."""
        self.nextdns = nextdns
        self.profile_id = profile_id
        self.profile_name = nextdns.get_profile_name(profile_id)
        self.device_info = DeviceInfo(
            configuration_url=f"https://my.nextdns.io/{profile_id}/setup",
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, str(profile_id))},
            manufacturer="NextDNS Inc.",
            name=self.profile_name,
        )

        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval)

    async def _async_update_data(self) -> NextDnsData:
        """Update data via library."""
        raise NotImplementedError("Update method not implemented")


class NextDnsStatusUpdateCoordinator(NextDnsUpdateCoordinator):
    """Class to manage fetching NextDNS analytics status data from API."""

    async def _async_update_data(self) -> AnalyticsStatus:
        """Update data via library."""
        try:
            async with timeout(10):
                return await self.nextdns.get_analytics_status(self.profile_id)
        except (ApiError, ClientConnectorError, InvalidApiKeyError) as err:
            raise UpdateFailed(err) from err


class NextDnsDnssecUpdateCoordinator(NextDnsUpdateCoordinator):
    """Class to manage fetching NextDNS analytics Dnssec data from API."""

    async def _async_update_data(self) -> AnalyticsDnssec:
        """Update data via library."""
        try:
            async with timeout(10):
                return await self.nextdns.get_analytics_dnssec(self.profile_id)
        except (ApiError, ClientConnectorError, InvalidApiKeyError) as err:
            raise UpdateFailed(err) from err


class NextDnsEncryptionUpdateCoordinator(NextDnsUpdateCoordinator):
    """Class to manage fetching NextDNS analytics encryption data from API."""

    async def _async_update_data(self) -> AnalyticsEncryption:
        """Update data via library."""
        try:
            async with timeout(10):
                return await self.nextdns.get_analytics_encryption(self.profile_id)
        except (ApiError, ClientConnectorError, InvalidApiKeyError) as err:
            raise UpdateFailed(err) from err


class NextDnsIpVersionsUpdateCoordinator(NextDnsUpdateCoordinator):
    """Class to manage fetching NextDNS analytics IP versions data from API."""

    async def _async_update_data(self) -> AnalyticsIpVersions:
        """Update data via library."""
        try:
            async with timeout(10):
                return await self.nextdns.get_analytics_ip_versions(self.profile_id)
        except (ApiError, ClientConnectorError, InvalidApiKeyError) as err:
            raise UpdateFailed(err) from err


class NextDnsProtocolsUpdateCoordinator(NextDnsUpdateCoordinator):
    """Class to manage fetching NextDNS analytics protocols data from API."""

    async def _async_update_data(self) -> AnalyticsProtocols:
        """Update data via library."""
        try:
            async with timeout(10):
                return await self.nextdns.get_analytics_protocols(self.profile_id)
        except (ApiError, ClientConnectorError, InvalidApiKeyError) as err:
            raise UpdateFailed(err) from err


_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BUTTON, Platform.SENSOR]
COORDINATORS = [
    (ATTR_DNSSEC, NextDnsDnssecUpdateCoordinator, UPDATE_INTERVAL_ANALYTICS),
    (ATTR_ENCRYPTION, NextDnsEncryptionUpdateCoordinator, UPDATE_INTERVAL_ANALYTICS),
    (ATTR_IP_VERSIONS, NextDnsIpVersionsUpdateCoordinator, UPDATE_INTERVAL_ANALYTICS),
    (ATTR_PROTOCOLS, NextDnsProtocolsUpdateCoordinator, UPDATE_INTERVAL_ANALYTICS),
    (ATTR_STATUS, NextDnsStatusUpdateCoordinator, UPDATE_INTERVAL_ANALYTICS),
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up NextDNS as config entry."""
    api_key = entry.data[CONF_API_KEY]
    profile_id = entry.data[CONF_PROFILE_ID]

    websession = async_get_clientsession(hass)
    try:
        async with timeout(10):
            nextdns = await NextDns.create(websession, api_key)
    except (ApiError, ClientConnectorError, asyncio.TimeoutError) as err:
        raise ConfigEntryNotReady from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {}

    tasks = []

    # Independent DataUpdateCoordinator is used for each API endpoint to avoid
    # unnecessary requests when entities using this endpoint are disabled.
    for coordinator_name, coordinator_class, update_interval in COORDINATORS:
        hass.data[DOMAIN][entry.entry_id][coordinator_name] = coordinator_class(
            hass, nextdns, profile_id, update_interval
        )
        tasks.append(
            hass.data[DOMAIN][entry.entry_id][
                coordinator_name
            ].async_config_entry_first_refresh()
        )

    await asyncio.gather(*tasks)

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok: bool = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
