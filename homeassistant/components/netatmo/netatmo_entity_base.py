"""Base class for Netatmo entities."""
from __future__ import annotations

from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo, Entity

from .const import (
    DATA_DEVICE_IDS,
    DEFAULT_ATTRIBUTION,
    DOMAIN,
    MANUFACTURER,
    MODELS,
    SIGNAL_NAME,
)
from .data_handler import PUBLICDATA_DATA_CLASS_NAME, NetatmoDataHandler


class NetatmoBase(Entity):
    """Netatmo entity base class."""

    def __init__(self, data_handler: NetatmoDataHandler) -> None:
        """Set up Netatmo entity base."""
        self.data_handler = data_handler
        self._data_classes: list[dict] = []

        self._device_name: str = ""
        self._id: str = ""
        self._model: str = ""
        self._netatmo_type: str = ""
        self._attr_name = None
        self._attr_unique_id = None
        self._attr_extra_state_attributes = {ATTR_ATTRIBUTION: DEFAULT_ATTRIBUTION}

    async def async_added_to_hass(self) -> None:
        """Entity created."""
        for data_class in self._data_classes:
            signal_name = data_class[SIGNAL_NAME]

            if "home_id" in data_class:
                await self.data_handler.register_data_class(
                    data_class["name"],
                    signal_name,
                    self.async_update_callback,
                    home_id=data_class["home_id"],
                )

            elif data_class["name"] == PUBLICDATA_DATA_CLASS_NAME:
                await self.data_handler.register_data_class(
                    data_class["name"],
                    signal_name,
                    self.async_update_callback,
                    lat_ne=data_class["lat_ne"],
                    lon_ne=data_class["lon_ne"],
                    lat_sw=data_class["lat_sw"],
                    lon_sw=data_class["lon_sw"],
                )

            else:
                await self.data_handler.register_data_class(
                    data_class["name"], signal_name, self.async_update_callback
                )

            for sub in self.data_handler.data_classes[signal_name].subscriptions:
                if sub is None:
                    await self.data_handler.unregister_data_class(signal_name, None)

        registry = dr.async_get(self.hass)
        if device := registry.async_get_device({(DOMAIN, self._id)}):
            self.hass.data[DOMAIN][DATA_DEVICE_IDS][self._id] = device.id

        self.async_update_callback()

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        await super().async_will_remove_from_hass()

        for data_class in self._data_classes:
            await self.data_handler.unregister_data_class(
                data_class[SIGNAL_NAME], self.async_update_callback
            )

    @callback
    def async_update_callback(self) -> None:
        """Update the entity's state."""
        raise NotImplementedError

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info for the sensor."""
        return DeviceInfo(
            configuration_url=f"https://my.netatmo.com/app/{self._netatmo_type}",
            identifiers={(DOMAIN, self._id)},
            name=self._device_name,
            manufacturer=MANUFACTURER,
            model=MODELS[self._model],
        )
