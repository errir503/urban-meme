"""Home Assistant representation of an UPnP/IGD."""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from async_upnp_client.aiohttp import AiohttpSessionRequester
from async_upnp_client.client import UpnpDevice
from async_upnp_client.client_factory import UpnpFactory
from async_upnp_client.exceptions import UpnpError
from async_upnp_client.profiles.igd import IgdDevice, StatusInfo

from homeassistant.components import ssdp
from homeassistant.components.ssdp import SsdpChange, SsdpServiceInfo
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.dt import utcnow

from .const import (
    BYTES_RECEIVED,
    BYTES_SENT,
    LOGGER as _LOGGER,
    PACKETS_RECEIVED,
    PACKETS_SENT,
    ROUTER_IP,
    ROUTER_UPTIME,
    TIMESTAMP,
    WAN_STATUS,
)


async def async_create_upnp_device(
    hass: HomeAssistant, ssdp_location: str
) -> UpnpDevice:
    """Create UPnP device."""
    session = async_get_clientsession(hass)
    requester = AiohttpSessionRequester(session, with_sleep=True, timeout=20)

    factory = UpnpFactory(requester, disable_state_variable_validation=True)
    return await factory.async_create_device(ssdp_location)


class Device:
    """Home Assistant representation of a UPnP/IGD device."""

    def __init__(self, hass: HomeAssistant, igd_device: IgdDevice) -> None:
        """Initialize UPnP/IGD device."""
        self.hass = hass
        self._igd_device = igd_device
        self.coordinator: DataUpdateCoordinator | None = None

    @classmethod
    async def async_create_device(
        cls, hass: HomeAssistant, ssdp_location: str
    ) -> Device:
        """Create UPnP/IGD device."""
        upnp_device = await async_create_upnp_device(hass, ssdp_location)

        # Create profile wrapper.
        igd_device = IgdDevice(upnp_device, None)
        device = cls(hass, igd_device)

        # Register SSDP callback for updates.
        usn = f"{upnp_device.udn}::{upnp_device.device_type}"
        await ssdp.async_register_callback(
            hass, device.async_ssdp_callback, {"usn": usn}
        )

        return device

    async def async_ssdp_callback(
        self, service_info: SsdpServiceInfo, change: SsdpChange
    ) -> None:
        """SSDP callback, update if needed."""
        _LOGGER.debug(
            "SSDP Callback, change: %s, headers: %s", change, service_info.ssdp_headers
        )
        if service_info.ssdp_location is None:
            return

        if change == SsdpChange.ALIVE:
            # We care only about updates.
            return

        device = self._igd_device.device
        if service_info.ssdp_location == device.device_url:
            return

        new_upnp_device = await async_create_upnp_device(
            self.hass, service_info.ssdp_location
        )
        device.reinit(new_upnp_device)

    @property
    def udn(self) -> str:
        """Get the UDN."""
        return self._igd_device.udn

    @property
    def name(self) -> str:
        """Get the name."""
        return self._igd_device.name

    @property
    def manufacturer(self) -> str:
        """Get the manufacturer."""
        return self._igd_device.manufacturer

    @property
    def model_name(self) -> str:
        """Get the model name."""
        return self._igd_device.model_name

    @property
    def device_type(self) -> str:
        """Get the device type."""
        return self._igd_device.device_type

    @property
    def usn(self) -> str:
        """Get the USN."""
        return f"{self.udn}::{self.device_type}"

    @property
    def unique_id(self) -> str:
        """Get the unique id."""
        return self.usn

    @property
    def hostname(self) -> str | None:
        """Get the hostname."""
        url = self._igd_device.device.device_url
        parsed = urlparse(url)
        return parsed.hostname

    def __str__(self) -> str:
        """Get string representation."""
        return f"IGD Device: {self.name}/{self.udn}::{self.device_type}"

    async def async_get_traffic_data(self) -> Mapping[str, Any]:
        """
        Get all traffic data in one go.

        Traffic data consists of:
        - total bytes sent
        - total bytes received
        - total packets sent
        - total packats received

        Data is timestamped.
        """
        _LOGGER.debug("Getting traffic statistics from device: %s", self)

        values = await asyncio.gather(
            self._igd_device.async_get_total_bytes_received(),
            self._igd_device.async_get_total_bytes_sent(),
            self._igd_device.async_get_total_packets_received(),
            self._igd_device.async_get_total_packets_sent(),
        )

        return {
            TIMESTAMP: utcnow(),
            BYTES_RECEIVED: values[0],
            BYTES_SENT: values[1],
            PACKETS_RECEIVED: values[2],
            PACKETS_SENT: values[3],
        }

    async def async_get_status(self) -> Mapping[str, Any]:
        """Get connection status, uptime, and external IP."""
        _LOGGER.debug("Getting status for device: %s", self)

        values = await asyncio.gather(
            self._igd_device.async_get_status_info(),
            self._igd_device.async_get_external_ip_address(),
            return_exceptions=True,
        )
        status_info: StatusInfo | None = None
        ip_address: str | None = None

        for idx, value in enumerate(values):
            if isinstance(value, UpnpError):
                # Not all routers support some of these items although based
                # on defined standard they should.
                _LOGGER.debug(
                    "Exception occurred while trying to get status %s for device %s: %s",
                    "status" if idx == 1 else "external IP address",
                    self,
                    str(value),
                )
                continue

            if isinstance(value, Exception):
                raise value

            if isinstance(value, StatusInfo):
                status_info = value
            elif isinstance(value, str):
                ip_address = value

        return {
            WAN_STATUS: status_info[0] if status_info is not None else None,
            ROUTER_UPTIME: status_info[2] if status_info is not None else None,
            ROUTER_IP: ip_address,
        }
