"""The BTHome Bluetooth integration."""
from __future__ import annotations

import logging

from bthome_ble import BTHomeBluetoothDeviceData, SensorUpdate
from bthome_ble.parser import EncryptionScheme

from homeassistant.components.bluetooth import (
    DOMAIN as BLUETOOTH_DOMAIN,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import (
    CONNECTION_BLUETOOTH,
    DeviceRegistry,
    async_get,
)

from .const import (
    BTHOME_BLE_EVENT,
    CONF_BINDKEY,
    CONF_DISCOVERED_EVENT_CLASSES,
    CONF_SLEEPY_DEVICE,
    DOMAIN,
    BTHomeBleEvent,
)
from .coordinator import BTHomePassiveBluetoothProcessorCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)


def process_service_info(
    hass: HomeAssistant,
    entry: ConfigEntry,
    data: BTHomeBluetoothDeviceData,
    service_info: BluetoothServiceInfoBleak,
    device_registry: DeviceRegistry,
) -> SensorUpdate:
    """Process a BluetoothServiceInfoBleak, running side effects and returning sensor data."""
    update = data.update(service_info)
    coordinator: BTHomePassiveBluetoothProcessorCoordinator = hass.data[DOMAIN][
        entry.entry_id
    ]
    discovered_device_classes = coordinator.discovered_device_classes
    if entry.data.get(CONF_SLEEPY_DEVICE, False) != data.sleepy_device:
        hass.config_entries.async_update_entry(
            entry,
            data=entry.data | {CONF_SLEEPY_DEVICE: data.sleepy_device},
        )
    if update.events:
        address = service_info.device.address
        for device_key, event in update.events.items():
            sensor_device_info = update.devices[device_key.device_id]
            device = device_registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                connections={(CONNECTION_BLUETOOTH, address)},
                identifiers={(BLUETOOTH_DOMAIN, address)},
                manufacturer=sensor_device_info.manufacturer,
                model=sensor_device_info.model,
                name=sensor_device_info.name,
                sw_version=sensor_device_info.sw_version,
                hw_version=sensor_device_info.hw_version,
            )
            event_class = event.device_key.key
            event_type = event.event_type

            if event_class not in discovered_device_classes:
                discovered_device_classes.add(event_class)
                hass.config_entries.async_update_entry(
                    entry,
                    data=entry.data
                    | {CONF_DISCOVERED_EVENT_CLASSES: list(discovered_device_classes)},
                )

            hass.bus.async_fire(
                BTHOME_BLE_EVENT,
                dict(
                    BTHomeBleEvent(
                        device_id=device.id,
                        address=address,
                        event_class=event_class,  # ie 'button'
                        event_type=event_type,  # ie 'press'
                        event_properties=event.event_properties,
                    )
                ),
            )

    # If payload is encrypted and the bindkey is not verified then we need to reauth
    if data.encryption_scheme != EncryptionScheme.NONE and not data.bindkey_verified:
        entry.async_start_reauth(hass, data={"device": data})

    return update


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BTHome Bluetooth from a config entry."""
    address = entry.unique_id
    assert address is not None

    kwargs = {}
    if bindkey := entry.data.get(CONF_BINDKEY):
        kwargs[CONF_BINDKEY] = bytes.fromhex(bindkey)
    data = BTHomeBluetoothDeviceData(**kwargs)

    device_registry = async_get(hass)
    coordinator = hass.data.setdefault(DOMAIN, {})[
        entry.entry_id
    ] = BTHomePassiveBluetoothProcessorCoordinator(
        hass,
        _LOGGER,
        address=address,
        mode=BluetoothScanningMode.PASSIVE,
        update_method=lambda service_info: process_service_info(
            hass, entry, data, service_info, device_registry
        ),
        device_data=data,
        discovered_device_classes=set(
            entry.data.get(CONF_DISCOVERED_EVENT_CLASSES, [])
        ),
        connectable=False,
        entry=entry,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(
        coordinator.async_start()
    )  # only start after all platforms have had a chance to subscribe
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
