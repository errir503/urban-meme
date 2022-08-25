"""Support for Freebox Delta, Revolution and Mini 4K."""
from __future__ import annotations

import logging
from typing import Any

from freebox_api.exceptions import InsufficientPermissionsError

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .router import FreeboxRouter

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the switch."""
    router: FreeboxRouter = hass.data[DOMAIN][entry.unique_id]
    async_add_entities([FreeboxWifiSwitch(router)], True)


class FreeboxWifiSwitch(SwitchEntity):
    """Representation of a freebox wifi switch."""

    def __init__(self, router: FreeboxRouter) -> None:
        """Initialize the Wifi switch."""
        self._name = "Freebox WiFi"
        self._state: bool | None = None
        self._router = router
        self._unique_id = f"{self._router.mac} {self._name}"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return self._name

    @property
    def is_on(self) -> bool | None:
        """Return true if device is on."""
        return self._state

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        return self._router.device_info

    async def _async_set_state(self, enabled: bool):
        """Turn the switch on or off."""
        wifi_config = {"enabled": enabled}
        try:
            await self._router.wifi.set_global_config(wifi_config)
        except InsufficientPermissionsError:
            _LOGGER.warning(
                "Home Assistant does not have permissions to modify the Freebox settings. Please refer to documentation"
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._async_set_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._async_set_state(False)

    async def async_update(self) -> None:
        """Get the state and update it."""
        datas = await self._router.wifi.get_global_config()
        active = datas["enabled"]
        self._state = bool(active)
