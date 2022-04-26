"""Open ports in your router for Home Assistant and provide statistics."""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from ipaddress import ip_address
from typing import Any

from async_upnp_client.exceptions import UpnpCommunicationError, UpnpConnectionError
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import ssdp
from homeassistant.components.binary_sensor import BinarySensorEntityDescription
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    CONF_LOCAL_IP,
    CONFIG_ENTRY_MAC_ADDRESS,
    CONFIG_ENTRY_ORIGINAL_UDN,
    CONFIG_ENTRY_ST,
    CONFIG_ENTRY_UDN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
)
from .device import Device, async_get_mac_address_from_host

NOTIFICATION_ID = "upnp_notification"
NOTIFICATION_TITLE = "UPnP/IGD Setup"

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

CONFIG_SCHEMA = vol.Schema(
    vol.All(
        cv.deprecated(DOMAIN),
        {
            DOMAIN: vol.Schema(
                vol.All(
                    cv.deprecated(CONF_LOCAL_IP),
                    {
                        vol.Optional(CONF_LOCAL_IP): vol.All(ip_address, cv.string),
                    },
                )
            )
        },
    ),
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up UPnP component."""
    hass.data[DOMAIN] = {}

    # Only start if set up via configuration.yaml.
    if DOMAIN in config:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_IMPORT}
            )
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up UPnP/IGD device from a config entry."""
    LOGGER.debug("Setting up config entry: %s", entry.entry_id)

    udn = entry.data[CONFIG_ENTRY_UDN]
    st = entry.data[CONFIG_ENTRY_ST]  # pylint: disable=invalid-name
    usn = f"{udn}::{st}"

    # Register device discovered-callback.
    device_discovered_event = asyncio.Event()
    discovery_info: ssdp.SsdpServiceInfo | None = None

    async def device_discovered(
        headers: ssdp.SsdpServiceInfo, change: ssdp.SsdpChange
    ) -> None:
        if change == ssdp.SsdpChange.BYEBYE:
            return

        nonlocal discovery_info
        LOGGER.debug("Device discovered: %s, at: %s", usn, headers.ssdp_location)
        discovery_info = headers
        device_discovered_event.set()

    cancel_discovered_callback = await ssdp.async_register_callback(
        hass,
        device_discovered,
        {
            "usn": usn,
        },
    )

    try:
        await asyncio.wait_for(device_discovered_event.wait(), timeout=10)
    except asyncio.TimeoutError as err:
        LOGGER.debug("Device not discovered: %s", usn)
        raise ConfigEntryNotReady from err
    finally:
        cancel_discovered_callback()

    # Create device.
    assert discovery_info is not None
    assert discovery_info.ssdp_location is not None
    location = discovery_info.ssdp_location
    try:
        device = await Device.async_create_device(hass, location)
    except UpnpConnectionError as err:
        LOGGER.debug(
            "Error connecting to device at location: %s, err: %s", location, err
        )
        raise ConfigEntryNotReady from err

    # Track the original UDN such that existing sensors do not change their unique_id.
    if CONFIG_ENTRY_ORIGINAL_UDN not in entry.data:
        hass.config_entries.async_update_entry(
            entry=entry,
            data={
                **entry.data,
                CONFIG_ENTRY_ORIGINAL_UDN: device.udn,
            },
        )
    device.original_udn = entry.data[CONFIG_ENTRY_ORIGINAL_UDN]

    # Store mac address for changed UDN matching.
    if device.host:
        device.mac_address = await async_get_mac_address_from_host(hass, device.host)
    if device.mac_address and not entry.data.get("CONFIG_ENTRY_MAC_ADDRESS"):
        hass.config_entries.async_update_entry(
            entry=entry,
            data={
                **entry.data,
                CONFIG_ENTRY_MAC_ADDRESS: device.mac_address,
            },
        )

    connections = {(dr.CONNECTION_UPNP, device.udn)}
    if device.mac_address:
        connections.add((dr.CONNECTION_NETWORK_MAC, device.mac_address))

    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get_device(
        identifiers=set(), connections=connections
    )
    if device_entry:
        LOGGER.debug(
            "Found device using connections: %s, device_entry: %s",
            connections,
            device_entry,
        )
    if not device_entry:
        # No device found, create new device entry.
        device_entry = device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            connections=connections,
            identifiers={(DOMAIN, device.usn)},
            name=device.name,
            manufacturer=device.manufacturer,
            model=device.model_name,
        )
        LOGGER.debug(
            "Created device using UDN '%s', device_entry: %s", device.udn, device_entry
        )
    else:
        # Update identifier.
        device_entry = device_registry.async_update_device(
            device_entry.id,
            new_identifiers={(DOMAIN, device.usn)},
        )

    assert device_entry
    update_interval = timedelta(seconds=DEFAULT_SCAN_INTERVAL)
    coordinator = UpnpDataUpdateCoordinator(
        hass,
        device=device,
        device_entry=device_entry,
        update_interval=update_interval,
    )

    # Try an initial refresh.
    await coordinator.async_config_entry_first_refresh()

    # Save coordinator.
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Setup platforms, creating sensors/binary_sensors.
    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a UPnP/IGD device from a config entry."""
    LOGGER.debug("Unloading config entry: %s", entry.entry_id)

    # Unload platforms.
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        del hass.data[DOMAIN][entry.entry_id]

    return unload_ok


@dataclass
class UpnpBinarySensorEntityDescription(BinarySensorEntityDescription):
    """A class that describes UPnP entities."""

    format: str = "s"
    unique_id: str | None = None


@dataclass
class UpnpSensorEntityDescription(SensorEntityDescription):
    """A class that describes a sensor UPnP entities."""

    format: str = "s"
    unique_id: str | None = None


class UpnpDataUpdateCoordinator(DataUpdateCoordinator):
    """Define an object to update data from UPNP device."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: Device,
        device_entry: dr.DeviceEntry,
        update_interval: timedelta,
    ) -> None:
        """Initialize."""
        self.device = device
        self.device_entry = device_entry

        super().__init__(
            hass,
            LOGGER,
            name=device.name,
            update_interval=update_interval,
            update_method=self._async_fetch_data,
        )

    async def _async_fetch_data(self) -> Mapping[str, Any]:
        """Update data."""
        try:
            update_values = await asyncio.gather(
                self.device.async_get_traffic_data(),
                self.device.async_get_status(),
            )

            return {
                **update_values[0],
                **update_values[1],
            }
        except UpnpCommunicationError as exception:
            LOGGER.debug(
                "Caught exception when updating device: %s, exception: %s",
                self.device,
                exception,
            )
            raise UpdateFailed(
                f"Unable to communicate with IGD at: {self.device.device_url}"
            ) from exception


class UpnpEntity(CoordinatorEntity[UpnpDataUpdateCoordinator]):
    """Base class for UPnP/IGD entities."""

    entity_description: UpnpSensorEntityDescription | UpnpBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: UpnpDataUpdateCoordinator,
        entity_description: UpnpSensorEntityDescription
        | UpnpBinarySensorEntityDescription,
    ) -> None:
        """Initialize the base entities."""
        super().__init__(coordinator)
        self._device = coordinator.device
        self.entity_description = entity_description
        self._attr_name = f"{coordinator.device.name} {entity_description.name}"
        self._attr_unique_id = f"{coordinator.device.original_udn}_{entity_description.unique_id or entity_description.key}"
        self._attr_device_info = DeviceInfo(
            connections=coordinator.device_entry.connections,
            name=coordinator.device_entry.name,
            manufacturer=coordinator.device_entry.manufacturer,
            model=coordinator.device_entry.model,
            configuration_url=coordinator.device_entry.configuration_url,
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and (
            self.coordinator.data.get(self.entity_description.key) is not None
        )
