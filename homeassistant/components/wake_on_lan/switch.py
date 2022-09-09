"""Support for wake on lan."""
from __future__ import annotations

import logging
import subprocess as sp
from typing import Any

import voluptuous as vol
import wakeonlan

from homeassistant.components.switch import PLATFORM_SCHEMA, SwitchEntity
from homeassistant.const import (
    CONF_BROADCAST_ADDRESS,
    CONF_BROADCAST_PORT,
    CONF_HOST,
    CONF_MAC,
    CONF_NAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.script import Script
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CONF_OFF_ACTION = "turn_off"

DEFAULT_NAME = "Wake on LAN"
DEFAULT_PING_TIMEOUT = 1

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_MAC): cv.string,
        vol.Optional(CONF_BROADCAST_ADDRESS): cv.string,
        vol.Optional(CONF_BROADCAST_PORT): cv.port,
        vol.Optional(CONF_HOST): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_OFF_ACTION): cv.SCRIPT_SCHEMA,
    }
)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up a wake on lan switch."""
    broadcast_address = config.get(CONF_BROADCAST_ADDRESS)
    broadcast_port = config.get(CONF_BROADCAST_PORT)
    host = config.get(CONF_HOST)
    mac_address = config[CONF_MAC]
    name = config[CONF_NAME]
    off_action = config.get(CONF_OFF_ACTION)

    add_entities(
        [
            WolSwitch(
                hass,
                name,
                host,
                mac_address,
                off_action,
                broadcast_address,
                broadcast_port,
            )
        ],
        host is not None,
    )


class WolSwitch(SwitchEntity):
    """Representation of a wake on lan switch."""

    def __init__(
        self,
        hass,
        name,
        host,
        mac_address,
        off_action,
        broadcast_address,
        broadcast_port,
    ):
        """Initialize the WOL switch."""
        self._hass = hass
        self._name = name
        self._host = host
        self._mac_address = mac_address
        self._broadcast_address = broadcast_address
        self._broadcast_port = broadcast_port
        self._off_script = (
            Script(hass, off_action, name, DOMAIN) if off_action else None
        )
        self._state = False
        self._assumed_state = host is None
        self._unique_id = dr.format_mac(mac_address)

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self._state

    @property
    def name(self):
        """Return the name of the switch."""
        return self._name

    @property
    def assumed_state(self):
        """Return true if no host is provided."""
        return self._assumed_state

    @property
    def should_poll(self):
        """Return false if assumed state is true."""
        return not self._assumed_state

    @property
    def unique_id(self):
        """Return the unique id of this switch."""
        return self._unique_id

    def turn_on(self, **kwargs: Any) -> None:
        """Turn the device on."""
        service_kwargs = {}
        if self._broadcast_address is not None:
            service_kwargs["ip_address"] = self._broadcast_address
        if self._broadcast_port is not None:
            service_kwargs["port"] = self._broadcast_port

        _LOGGER.info(
            "Send magic packet to mac %s (broadcast: %s, port: %s)",
            self._mac_address,
            self._broadcast_address,
            self._broadcast_port,
        )

        wakeonlan.send_magic_packet(self._mac_address, **service_kwargs)

        if self._assumed_state:
            self._state = True
            self.async_write_ha_state()

    def turn_off(self, **kwargs: Any) -> None:
        """Turn the device off if an off action is present."""
        if self._off_script is not None:
            self._off_script.run(context=self._context)

        if self._assumed_state:
            self._state = False
            self.async_write_ha_state()

    def update(self) -> None:
        """Check if device is on and update the state. Only called if assumed state is false."""
        ping_cmd = [
            "ping",
            "-c",
            "1",
            "-W",
            str(DEFAULT_PING_TIMEOUT),
            str(self._host),
        ]

        status = sp.call(ping_cmd, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        self._state = not bool(status)
