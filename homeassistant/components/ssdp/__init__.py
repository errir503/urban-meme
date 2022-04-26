"""The SSDP integration."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from ipaddress import IPv4Address, IPv6Address
import logging
from typing import Any

from async_upnp_client.aiohttp import AiohttpSessionRequester
from async_upnp_client.const import AddressTupleVXType, DeviceOrServiceType, SsdpSource
from async_upnp_client.description_cache import DescriptionCache
from async_upnp_client.ssdp import SSDP_PORT, determine_source_target, is_ipv4_address
from async_upnp_client.ssdp_listener import SsdpDevice, SsdpDeviceTracker, SsdpListener
from async_upnp_client.utils import CaseInsensitiveDict

from homeassistant import config_entries
from homeassistant.components import network
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, MATCH_ALL
from homeassistant.core import HomeAssistant, callback as core_callback
from homeassistant.data_entry_flow import BaseServiceInfo
from homeassistant.helpers import discovery_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.frame import report
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_ssdp, bind_hass

DOMAIN = "ssdp"
SCAN_INTERVAL = timedelta(minutes=2)

IPV4_BROADCAST = IPv4Address("255.255.255.255")

# Attributes for accessing info from SSDP response
ATTR_SSDP_LOCATION = "ssdp_location"
ATTR_SSDP_ST = "ssdp_st"
ATTR_SSDP_NT = "ssdp_nt"
ATTR_SSDP_UDN = "ssdp_udn"
ATTR_SSDP_USN = "ssdp_usn"
ATTR_SSDP_EXT = "ssdp_ext"
ATTR_SSDP_SERVER = "ssdp_server"
ATTR_SSDP_BOOTID = "BOOTID.UPNP.ORG"
ATTR_SSDP_NEXTBOOTID = "NEXTBOOTID.UPNP.ORG"
# Attributes for accessing info from retrieved UPnP device description
ATTR_UPNP_DEVICE_TYPE = "deviceType"
ATTR_UPNP_FRIENDLY_NAME = "friendlyName"
ATTR_UPNP_MANUFACTURER = "manufacturer"
ATTR_UPNP_MANUFACTURER_URL = "manufacturerURL"
ATTR_UPNP_MODEL_DESCRIPTION = "modelDescription"
ATTR_UPNP_MODEL_NAME = "modelName"
ATTR_UPNP_MODEL_NUMBER = "modelNumber"
ATTR_UPNP_MODEL_URL = "modelURL"
ATTR_UPNP_SERIAL = "serialNumber"
ATTR_UPNP_SERVICE_LIST = "serviceList"
ATTR_UPNP_UDN = "UDN"
ATTR_UPNP_UPC = "UPC"
ATTR_UPNP_PRESENTATION_URL = "presentationURL"
# Attributes for accessing info added by Home Assistant
ATTR_HA_MATCHING_DOMAINS = "x_homeassistant_matching_domains"

PRIMARY_MATCH_KEYS = [ATTR_UPNP_MANUFACTURER, "st", ATTR_UPNP_DEVICE_TYPE, "nt"]

_LOGGER = logging.getLogger(__name__)


@dataclass
class _HaServiceDescription:
    """Keys added by HA."""

    x_homeassistant_matching_domains: set[str] = field(default_factory=set)


@dataclass
class _SsdpServiceDescription:
    """SSDP info with optional keys."""

    ssdp_usn: str
    ssdp_st: str
    ssdp_location: str | None = None
    ssdp_nt: str | None = None
    ssdp_udn: str | None = None
    ssdp_ext: str | None = None
    ssdp_server: str | None = None
    ssdp_headers: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class _UpnpServiceDescription:
    """UPnP info."""

    upnp: Mapping[str, Any]


@dataclass
class SsdpServiceInfo(
    _HaServiceDescription,
    _SsdpServiceDescription,
    _UpnpServiceDescription,
    BaseServiceInfo,
):
    """Prepared info from ssdp/upnp entries."""

    def __getitem__(self, name: str) -> Any:
        """
        Allow property access by name for compatibility reason.

        Deprecated, and will be removed in version 2022.6.
        """
        report(
            f"accessed discovery_info['{name}'] instead of discovery_info.{name}, "
            f"discovery_info.upnp['{name}'] "
            f"or discovery_info.ssdp_headers['{name}']; "
            "this will fail in version 2022.6",
            exclude_integrations={DOMAIN},
            error_if_core=False,
        )
        # Use a property if it is available, fallback to upnp data
        if hasattr(self, name):
            return getattr(self, name)
        if name in self.ssdp_headers and name not in self.upnp:
            return self.ssdp_headers.get(name)
        return self.upnp[name]

    def get(self, name: str, default: Any = None) -> Any:
        """
        Enable method for compatibility reason.

        Deprecated, and will be removed in version 2022.6.
        """
        report(
            f"accessed discovery_info.get('{name}') instead of discovery_info.{name}, "
            f"discovery_info.upnp.get('{name}') "
            f"or discovery_info.ssdp_headers.get('{name}'); "
            "this will fail in version 2022.6",
            exclude_integrations={DOMAIN},
            error_if_core=False,
        )
        if hasattr(self, name):
            return getattr(self, name)
        return self.upnp.get(name, self.ssdp_headers.get(name, default))

    def __contains__(self, name: str) -> bool:
        """
        Enable method for compatibility reason.

        Deprecated, and will be removed in version 2022.6.
        """
        report(
            f"accessed discovery_info.__contains__('{name}') "
            f"instead of discovery_info.upnp.__contains__('{name}') "
            f"or discovery_info.ssdp_headers.__contains__('{name}'); "
            "this will fail in version 2022.6",
            exclude_integrations={DOMAIN},
            error_if_core=False,
        )
        if hasattr(self, name):
            return getattr(self, name) is not None
        return name in self.upnp or name in self.ssdp_headers


SsdpChange = Enum("SsdpChange", "ALIVE BYEBYE UPDATE")
SsdpCallback = Callable[[SsdpServiceInfo, SsdpChange], Awaitable]

SSDP_SOURCE_SSDP_CHANGE_MAPPING: Mapping[SsdpSource, SsdpChange] = {
    SsdpSource.SEARCH_ALIVE: SsdpChange.ALIVE,
    SsdpSource.SEARCH_CHANGED: SsdpChange.ALIVE,
    SsdpSource.ADVERTISEMENT_ALIVE: SsdpChange.ALIVE,
    SsdpSource.ADVERTISEMENT_BYEBYE: SsdpChange.BYEBYE,
    SsdpSource.ADVERTISEMENT_UPDATE: SsdpChange.UPDATE,
}


@bind_hass
async def async_register_callback(
    hass: HomeAssistant,
    callback: SsdpCallback,
    match_dict: None | dict[str, str] = None,
) -> Callable[[], None]:
    """Register to receive a callback on ssdp broadcast.

    Returns a callback that can be used to cancel the registration.
    """
    scanner: Scanner = hass.data[DOMAIN]
    return await scanner.async_register_callback(callback, match_dict)


@bind_hass
async def async_get_discovery_info_by_udn_st(  # pylint: disable=invalid-name
    hass: HomeAssistant, udn: str, st: str
) -> SsdpServiceInfo | None:
    """Fetch the discovery info cache."""
    scanner: Scanner = hass.data[DOMAIN]
    return await scanner.async_get_discovery_info_by_udn_st(udn, st)


@bind_hass
async def async_get_discovery_info_by_st(  # pylint: disable=invalid-name
    hass: HomeAssistant, st: str
) -> list[SsdpServiceInfo]:
    """Fetch all the entries matching the st."""
    scanner: Scanner = hass.data[DOMAIN]
    return await scanner.async_get_discovery_info_by_st(st)


@bind_hass
async def async_get_discovery_info_by_udn(
    hass: HomeAssistant, udn: str
) -> list[SsdpServiceInfo]:
    """Fetch all the entries matching the udn."""
    scanner: Scanner = hass.data[DOMAIN]
    return await scanner.async_get_discovery_info_by_udn(udn)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the SSDP integration."""

    integration_matchers = IntegrationMatchers()
    integration_matchers.async_setup(await async_get_ssdp(hass))

    scanner = hass.data[DOMAIN] = Scanner(hass, integration_matchers)

    asyncio.create_task(scanner.async_start())

    return True


async def _async_process_callbacks(
    callbacks: list[SsdpCallback],
    discovery_info: SsdpServiceInfo,
    ssdp_change: SsdpChange,
) -> None:
    for callback in callbacks:
        try:
            await callback(discovery_info, ssdp_change)
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Failed to callback info: %s", discovery_info)


@core_callback
def _async_headers_match(
    headers: CaseInsensitiveDict, lower_match_dict: dict[str, str]
) -> bool:
    for header, val in lower_match_dict.items():
        if val == MATCH_ALL:
            if header not in headers:
                return False
        elif headers.get_lower(header) != val:
            return False
    return True


class IntegrationMatchers:
    """Optimized integration matching."""

    def __init__(self) -> None:
        """Init optimized integration matching."""
        self._match_by_key: dict[
            str, dict[str, list[tuple[str, dict[str, str]]]]
        ] | None = None

    @core_callback
    def async_setup(
        self, integration_matchers: dict[str, list[dict[str, str]]]
    ) -> None:
        """Build matchers by key.

        Here we convert the primary match keys into their own
        dicts so we can do lookups of the primary match
        key to find the match dict.
        """
        self._match_by_key = {}
        for key in PRIMARY_MATCH_KEYS:
            matchers_by_key = self._match_by_key[key] = {}
            for domain, matchers in integration_matchers.items():
                for matcher in matchers:
                    if match_value := matcher.get(key):
                        matchers_by_key.setdefault(match_value, []).append(
                            (domain, matcher)
                        )

    @core_callback
    def async_matching_domains(self, info_with_desc: CaseInsensitiveDict) -> set[str]:
        """Find domains matching the passed CaseInsensitiveDict."""
        assert self._match_by_key is not None
        domains = set()
        for key, matchers_by_key in self._match_by_key.items():
            if not (match_value := info_with_desc.get(key)):
                continue
            for domain, matcher in matchers_by_key.get(match_value, []):
                if domain in domains:
                    continue
                if all(info_with_desc.get(k) == v for (k, v) in matcher.items()):
                    domains.add(domain)
        return domains


class Scanner:
    """Class to manage SSDP searching and SSDP advertisements."""

    def __init__(
        self, hass: HomeAssistant, integration_matchers: IntegrationMatchers
    ) -> None:
        """Initialize class."""
        self.hass = hass
        self._cancel_scan: Callable[[], None] | None = None
        self._ssdp_listeners: list[SsdpListener] = []
        self._callbacks: list[tuple[SsdpCallback, dict[str, str]]] = []
        self._description_cache: DescriptionCache | None = None
        self.integration_matchers = integration_matchers

    @property
    def _ssdp_devices(self) -> list[SsdpDevice]:
        """Get all seen devices."""
        return [
            ssdp_device
            for ssdp_listener in self._ssdp_listeners
            for ssdp_device in ssdp_listener.devices.values()
        ]

    @property
    def _all_headers_from_ssdp_devices(
        self,
    ) -> dict[tuple[str, str], CaseInsensitiveDict]:
        return {
            (ssdp_device.udn, dst): headers
            for ssdp_device in self._ssdp_devices
            for dst, headers in ssdp_device.all_combined_headers.items()
        }

    async def async_register_callback(
        self, callback: SsdpCallback, match_dict: None | dict[str, str] = None
    ) -> Callable[[], None]:
        """Register a callback."""
        if match_dict is None:
            lower_match_dict = {}
        else:
            lower_match_dict = {k.lower(): v for k, v in match_dict.items()}

        # Make sure any entries that happened
        # before the callback was registered are fired
        for headers in self._all_headers_from_ssdp_devices.values():
            if _async_headers_match(headers, lower_match_dict):
                await _async_process_callbacks(
                    [callback],
                    await self._async_headers_to_discovery_info(headers),
                    SsdpChange.ALIVE,
                )

        callback_entry = (callback, lower_match_dict)
        self._callbacks.append(callback_entry)

        @core_callback
        def _async_remove_callback() -> None:
            self._callbacks.remove(callback_entry)

        return _async_remove_callback

    async def async_stop(self, *_: Any) -> None:
        """Stop the scanner."""
        assert self._cancel_scan is not None
        self._cancel_scan()

        await self._async_stop_ssdp_listeners()

    async def _async_stop_ssdp_listeners(self) -> None:
        """Stop the SSDP listeners."""
        await asyncio.gather(
            *(listener.async_stop() for listener in self._ssdp_listeners),
            return_exceptions=True,
        )

    async def _async_build_source_set(self) -> set[IPv4Address | IPv6Address]:
        """Build the list of ssdp sources."""
        return {
            source_ip
            for source_ip in await network.async_get_enabled_source_ips(self.hass)
            if not source_ip.is_loopback and not source_ip.is_global
        }

    async def async_scan(self, *_: Any) -> None:
        """Scan for new entries using ssdp listeners."""
        await self.async_scan_multicast()
        await self.async_scan_broadcast()

    async def async_scan_multicast(self, *_: Any) -> None:
        """Scan for new entries using multicase target."""
        for ssdp_listener in self._ssdp_listeners:
            await ssdp_listener.async_search()

    async def async_scan_broadcast(self, *_: Any) -> None:
        """Scan for new entries using broadcast target."""
        # Some sonos devices only seem to respond if we send to the broadcast
        # address. This matches pysonos' behavior
        # https://github.com/amelchio/pysonos/blob/d4329b4abb657d106394ae69357805269708c996/pysonos/discovery.py#L120
        for listener in self._ssdp_listeners:
            if is_ipv4_address(listener.source):
                await listener.async_search((str(IPV4_BROADCAST), SSDP_PORT))

    async def async_start(self) -> None:
        """Start the scanners."""
        session = async_get_clientsession(self.hass)
        requester = AiohttpSessionRequester(session, True, 10)
        self._description_cache = DescriptionCache(requester)

        await self._async_start_ssdp_listeners()

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self.async_stop)
        self._cancel_scan = async_track_time_interval(
            self.hass, self.async_scan, SCAN_INTERVAL
        )

        # Trigger the initial-scan.
        await self.async_scan()

    async def _async_start_ssdp_listeners(self) -> None:
        """Start the SSDP Listeners."""
        # Devices are shared between all sources.
        device_tracker = SsdpDeviceTracker()
        for source_ip in await self._async_build_source_set():
            source_ip_str = str(source_ip)
            if source_ip.version == 6:
                source_tuple: AddressTupleVXType = (
                    source_ip_str,
                    0,
                    0,
                    int(getattr(source_ip, "scope_id")),
                )
            else:
                source_tuple = (source_ip_str, 0)
            source, target = determine_source_target(source_tuple)
            self._ssdp_listeners.append(
                SsdpListener(
                    async_callback=self._ssdp_listener_callback,
                    source=source,
                    target=target,
                    device_tracker=device_tracker,
                )
            )
        results = await asyncio.gather(
            *(listener.async_start() for listener in self._ssdp_listeners),
            return_exceptions=True,
        )
        failed_listeners = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                _LOGGER.debug(
                    "Failed to setup listener for %s: %s",
                    self._ssdp_listeners[idx].source,
                    result,
                )
                failed_listeners.append(self._ssdp_listeners[idx])
        for listener in failed_listeners:
            self._ssdp_listeners.remove(listener)

    @core_callback
    def _async_get_matching_callbacks(
        self,
        combined_headers: CaseInsensitiveDict,
    ) -> list[SsdpCallback]:
        """Return a list of callbacks that match."""
        return [
            callback
            for callback, lower_match_dict in self._callbacks
            if _async_headers_match(combined_headers, lower_match_dict)
        ]

    async def _ssdp_listener_callback(
        self,
        ssdp_device: SsdpDevice,
        dst: DeviceOrServiceType,
        source: SsdpSource,
    ) -> None:
        """Handle a device/service change."""
        _LOGGER.debug(
            "SSDP: ssdp_device: %s, dst: %s, source: %s", ssdp_device, dst, source
        )

        location = ssdp_device.location
        info_desc = None
        combined_headers = ssdp_device.combined_headers(dst)
        callbacks = self._async_get_matching_callbacks(combined_headers)
        matching_domains: set[str] = set()

        # If there are no changes from a search, do not trigger a config flow
        if source != SsdpSource.SEARCH_ALIVE:
            info_desc = await self._async_get_description_dict(location) or {}
            matching_domains = self.integration_matchers.async_matching_domains(
                CaseInsensitiveDict(combined_headers.as_dict(), **info_desc)
            )

        if not callbacks and not matching_domains:
            return

        if info_desc is None:
            info_desc = await self._async_get_description_dict(location) or {}
        discovery_info = discovery_info_from_headers_and_description(
            combined_headers, info_desc
        )
        discovery_info.x_homeassistant_matching_domains = matching_domains
        ssdp_change = SSDP_SOURCE_SSDP_CHANGE_MAPPING[source]
        await _async_process_callbacks(callbacks, discovery_info, ssdp_change)

        # Config flows should only be created for alive/update messages from alive devices
        if ssdp_change == SsdpChange.BYEBYE:
            return

        _LOGGER.debug("Discovery info: %s", discovery_info)

        for domain in matching_domains:
            _LOGGER.debug("Discovered %s at %s", domain, location)
            discovery_flow.async_create_flow(
                self.hass,
                domain,
                {"source": config_entries.SOURCE_SSDP},
                discovery_info,
            )

    async def _async_get_description_dict(
        self, location: str | None
    ) -> Mapping[str, str]:
        """Get description dict."""
        assert self._description_cache is not None
        return await self._description_cache.async_get_description_dict(location) or {}

    async def _async_headers_to_discovery_info(
        self, headers: CaseInsensitiveDict
    ) -> SsdpServiceInfo:
        """Combine the headers and description into discovery_info.

        Building this is a bit expensive so we only do it on demand.
        """
        assert self._description_cache is not None
        location = headers["location"]
        info_desc = (
            await self._description_cache.async_get_description_dict(location) or {}
        )
        return discovery_info_from_headers_and_description(headers, info_desc)

    async def async_get_discovery_info_by_udn_st(  # pylint: disable=invalid-name
        self, udn: str, st: str
    ) -> SsdpServiceInfo | None:
        """Return discovery_info for a udn and st."""
        if headers := self._all_headers_from_ssdp_devices.get((udn, st)):
            return await self._async_headers_to_discovery_info(headers)
        return None

    async def async_get_discovery_info_by_st(  # pylint: disable=invalid-name
        self, st: str
    ) -> list[SsdpServiceInfo]:
        """Return matching discovery_infos for a st."""
        return [
            await self._async_headers_to_discovery_info(headers)
            for udn_st, headers in self._all_headers_from_ssdp_devices.items()
            if udn_st[1] == st
        ]

    async def async_get_discovery_info_by_udn(self, udn: str) -> list[SsdpServiceInfo]:
        """Return matching discovery_infos for a udn."""
        return [
            await self._async_headers_to_discovery_info(headers)
            for udn_st, headers in self._all_headers_from_ssdp_devices.items()
            if udn_st[0] == udn
        ]


def discovery_info_from_headers_and_description(
    combined_headers: CaseInsensitiveDict,
    info_desc: Mapping[str, Any],
) -> SsdpServiceInfo:
    """Convert headers and description to discovery_info."""
    ssdp_usn = combined_headers["usn"]
    ssdp_st = combined_headers.get("st")
    if isinstance(info_desc, CaseInsensitiveDict):
        upnp_info = {**info_desc.as_dict()}
    else:
        upnp_info = {**info_desc}

    # Increase compatibility: depending on the message type,
    # either the ST (Search Target, from M-SEARCH messages)
    # or NT (Notification Type, from NOTIFY messages) header is mandatory
    if not ssdp_st:
        ssdp_st = combined_headers["nt"]

    # Ensure UPnP "udn" is set
    if ATTR_UPNP_UDN not in upnp_info:
        if udn := _udn_from_usn(ssdp_usn):
            upnp_info[ATTR_UPNP_UDN] = udn

    return SsdpServiceInfo(
        ssdp_usn=ssdp_usn,
        ssdp_st=ssdp_st,
        ssdp_ext=combined_headers.get("ext"),
        ssdp_server=combined_headers.get("server"),
        ssdp_location=combined_headers.get("location"),
        ssdp_udn=combined_headers.get("_udn"),
        ssdp_nt=combined_headers.get("nt"),
        ssdp_headers=combined_headers,
        upnp=upnp_info,
    )


def _udn_from_usn(usn: str | None) -> str | None:
    """Get the UDN from the USN."""
    if usn is None:
        return None
    if usn.startswith("uuid:"):
        return usn.split("::")[0]
    return None
