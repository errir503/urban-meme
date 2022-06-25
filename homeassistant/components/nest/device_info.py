"""Library for extracting device specific information common to entities."""

from __future__ import annotations

from collections.abc import Mapping

from google_nest_sdm.device import Device
from google_nest_sdm.device_traits import InfoTrait

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo

from .const import DATA_DEVICE_MANAGER, DOMAIN

DEVICE_TYPE_MAP: dict[str, str] = {
    "sdm.devices.types.CAMERA": "Camera",
    "sdm.devices.types.DISPLAY": "Display",
    "sdm.devices.types.DOORBELL": "Doorbell",
    "sdm.devices.types.THERMOSTAT": "Thermostat",
}


class NestDeviceInfo:
    """Provide device info from the SDM device, shared across platforms."""

    device_brand = "Google Nest"

    def __init__(self, device: Device) -> None:
        """Initialize the DeviceInfo."""
        self._device = device

    @property
    def device_info(self) -> DeviceInfo:
        """Return device specific attributes."""
        return DeviceInfo(
            # The API "name" field is a unique device identifier.
            identifiers={(DOMAIN, self._device.name)},
            manufacturer=self.device_brand,
            model=self.device_model,
            name=self.device_name,
            suggested_area=self.suggested_area,
        )

    @property
    def device_name(self) -> str | None:
        """Return the name of the physical device that includes the sensor."""
        if InfoTrait.NAME in self._device.traits:
            trait: InfoTrait = self._device.traits[InfoTrait.NAME]
            if trait.custom_name:
                return str(trait.custom_name)
        # Build a name from the room/structure if not set explicitly
        if area := self.suggested_area:
            return area
        return self.device_model

    @property
    def device_model(self) -> str | None:
        """Return device model information."""
        # The API intentionally returns minimal information about specific
        # devices, instead relying on traits, but we can infer a generic model
        # name based on the type
        return DEVICE_TYPE_MAP.get(self._device.type)

    @property
    def suggested_area(self) -> str | None:
        """Return device suggested area based on the Google Home room."""
        if parent_relations := self._device.parent_relations:
            items = sorted(parent_relations.items())
            names = [name for id, name in items]
            return " ".join(names)
        return None


@callback
def async_nest_devices(hass: HomeAssistant) -> Mapping[str, Device]:
    """Return a mapping of all nest devices for all config entries."""
    devices = {}
    for entry_id in hass.data[DOMAIN]:
        if not (device_manager := hass.data[DOMAIN][entry_id].get(DATA_DEVICE_MANAGER)):
            continue
        devices.update(
            {device.name: device for device in device_manager.devices.values()}
        )
    return devices


@callback
def async_nest_devices_by_device_id(hass: HomeAssistant) -> Mapping[str, Device]:
    """Return a mapping of all nest devices by home assistant device id, for all config entries."""
    device_registry = dr.async_get(hass)
    devices = {}
    for nest_device_id, device in async_nest_devices(hass).items():
        if device_entry := device_registry.async_get_device({(DOMAIN, nest_device_id)}):
            devices[device_entry.id] = device
    return devices
