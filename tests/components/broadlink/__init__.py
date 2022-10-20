"""Tests for the Broadlink integration."""
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from homeassistant.components.broadlink.const import DOMAIN

from tests.common import MockConfigEntry

# Do not edit/remove. Adding is ok.
BROADLINK_DEVICES = {
    "Entrance": (
        "192.168.0.11",
        "34ea34befc25",
        "RM mini 3",
        "Broadlink",
        "RMMINI",
        0x2737,
        57,
        8,
    ),
    "Living Room": (
        "192.168.0.12",
        "34ea34b43b5a",
        "RM mini 3",
        "Broadlink",
        "RMMINIB",
        0x5F36,
        44017,
        10,
    ),
    "Office": (
        "192.168.0.13",
        "34ea34b43d22",
        "RM pro",
        "Broadlink",
        "RMPRO",
        0x2787,
        20025,
        7,
    ),
    "Garage": (
        "192.168.0.14",
        "34ea34c43f31",
        "RM4 pro",
        "Broadlink",
        "RM4PRO",
        0x6026,
        52,
        4,
    ),
    "Bedroom": (
        "192.168.0.15",
        "34ea34b45d2c",
        "e-Sensor",
        "Broadlink",
        "A1",
        0x2714,
        20025,
        5,
    ),
    "Dining room": (
        "192.168.0.16",
        "34ea34b4fd1c",
        "SCB1E",
        "Broadlink",
        "SP4B",
        0x5115,
        57,
        5,
    ),
    "Kitchen": (  # Not supported.
        "192.168.0.64",
        "34ea34b61d2c",
        "SB800TD",
        "Broadlink",
        "SB800TD",
        0x504E,
        57,
        5,
    ),
    "Gaming room": (
        "192.168.0.65",
        "34ea34b61d2d",
        "MP1-1K4S",
        "Broadlink",
        "MP1",
        0x4EB5,
        57,
        5,
    ),
}


@dataclass
class MockSetup:
    """Representation of a mock setup."""

    api: MagicMock
    entry: MockConfigEntry
    factory: MagicMock


class BroadlinkDevice:
    """Representation of a Broadlink device."""

    def __init__(
        self, name, host, mac, model, manufacturer, type_, devtype, fwversion, timeout
    ):
        """Initialize the device."""
        self.name: str = name
        self.host: str = host
        self.mac: str = mac
        self.model: str = model
        self.manufacturer: str = manufacturer
        self.type: str = type_
        self.devtype: int = devtype
        self.timeout: int = timeout
        self.fwversion: int = fwversion

    async def setup_entry(self, hass, mock_api=None, mock_entry=None):
        """Set up the device."""
        mock_api = mock_api or self.get_mock_api()
        mock_entry = mock_entry or self.get_mock_entry()
        mock_entry.add_to_hass(hass)

        with patch(
            "homeassistant.components.broadlink.device.blk.gendevice",
            return_value=mock_api,
        ) as mock_factory:
            await hass.config_entries.async_setup(mock_entry.entry_id)
            await hass.async_block_till_done()

        return MockSetup(mock_api, mock_entry, mock_factory)

    def get_mock_api(self):
        """Return a mock device (API)."""
        mock_api = MagicMock()
        mock_api.name = self.name
        mock_api.host = (self.host, 80)
        mock_api.mac = bytes.fromhex(self.mac)
        mock_api.model = self.model
        mock_api.manufacturer = self.manufacturer
        mock_api.type = self.type
        mock_api.devtype = self.devtype
        mock_api.timeout = self.timeout
        mock_api.is_locked = False
        mock_api.auth.return_value = True
        mock_api.get_fwversion.return_value = self.fwversion
        return mock_api

    def get_mock_entry(self):
        """Return a mock config entry."""
        return MockConfigEntry(
            domain=DOMAIN,
            unique_id=self.mac,
            title=self.name,
            data=self.get_entry_data(),
        )

    def get_entry_data(self):
        """Return entry data."""
        return {
            "host": self.host,
            "mac": self.mac,
            "type": self.devtype,
            "timeout": self.timeout,
        }


def get_device(name):
    """Get a device by name."""
    return BroadlinkDevice(name, *BROADLINK_DEVICES[name])
