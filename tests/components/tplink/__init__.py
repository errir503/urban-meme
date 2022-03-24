"""Tests for the TP-Link component."""

from unittest.mock import AsyncMock, MagicMock, patch

from kasa import (
    SmartBulb,
    SmartDevice,
    SmartDimmer,
    SmartLightStrip,
    SmartPlug,
    SmartStrip,
)
from kasa.exceptions import SmartDeviceException
from kasa.protocol import TPLinkSmartHomeProtocol

from homeassistant.components.tplink import CONF_HOST
from homeassistant.components.tplink.const import DOMAIN
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry

MODULE = "homeassistant.components.tplink"
MODULE_CONFIG_FLOW = "homeassistant.components.tplink.config_flow"
IP_ADDRESS = "127.0.0.1"
ALIAS = "My Bulb"
MODEL = "HS100"
MAC_ADDRESS = "aa:bb:cc:dd:ee:ff"
DEFAULT_ENTRY_TITLE = f"{ALIAS} {MODEL}"


def _mock_protocol() -> TPLinkSmartHomeProtocol:
    protocol = MagicMock(auto_spec=TPLinkSmartHomeProtocol)
    protocol.close = AsyncMock()
    return protocol


def _mocked_bulb() -> SmartBulb:
    bulb = MagicMock(auto_spec=SmartBulb, name="Mocked bulb")
    bulb.update = AsyncMock()
    bulb.mac = MAC_ADDRESS
    bulb.alias = ALIAS
    bulb.model = MODEL
    bulb.host = IP_ADDRESS
    bulb.brightness = 50
    bulb.color_temp = 4000
    bulb.is_color = True
    bulb.is_strip = False
    bulb.is_plug = False
    bulb.is_dimmer = False
    bulb.is_light_strip = False
    bulb.has_effects = False
    bulb.effect = None
    bulb.effect_list = None
    bulb.hsv = (10, 30, 5)
    bulb.device_id = MAC_ADDRESS
    bulb.valid_temperature_range.min = 4000
    bulb.valid_temperature_range.max = 9000
    bulb.hw_info = {"sw_ver": "1.0.0", "hw_ver": "1.0.0"}
    bulb.turn_off = AsyncMock()
    bulb.turn_on = AsyncMock()
    bulb.set_brightness = AsyncMock()
    bulb.set_hsv = AsyncMock()
    bulb.set_color_temp = AsyncMock()
    bulb.protocol = _mock_protocol()
    return bulb


class MockedSmartLightStrip(SmartLightStrip):
    """Mock a SmartLightStrip."""

    def __new__(cls, *args, **kwargs):
        """Mock a SmartLightStrip that will pass an isinstance check."""
        return MagicMock(spec=cls)


def _mocked_smart_light_strip() -> SmartLightStrip:
    strip = MockedSmartLightStrip()
    strip.update = AsyncMock()
    strip.mac = MAC_ADDRESS
    strip.alias = ALIAS
    strip.model = MODEL
    strip.host = IP_ADDRESS
    strip.brightness = 50
    strip.color_temp = 4000
    strip.is_color = True
    strip.is_strip = False
    strip.is_plug = False
    strip.is_dimmer = False
    strip.is_light_strip = True
    strip.has_effects = True
    strip.effect = {"name": "Effect1", "enable": 1}
    strip.effect_list = ["Effect1", "Effect2"]
    strip.hsv = (10, 30, 5)
    strip.device_id = MAC_ADDRESS
    strip.valid_temperature_range.min = 4000
    strip.valid_temperature_range.max = 9000
    strip.hw_info = {"sw_ver": "1.0.0", "hw_ver": "1.0.0"}
    strip.turn_off = AsyncMock()
    strip.turn_on = AsyncMock()
    strip.set_brightness = AsyncMock()
    strip.set_hsv = AsyncMock()
    strip.set_color_temp = AsyncMock()
    strip.set_effect = AsyncMock()
    strip.set_custom_effect = AsyncMock()
    strip.protocol = _mock_protocol()
    return strip


def _mocked_dimmer() -> SmartDimmer:
    dimmer = MagicMock(auto_spec=SmartDimmer, name="Mocked dimmer")
    dimmer.update = AsyncMock()
    dimmer.mac = MAC_ADDRESS
    dimmer.alias = "My Dimmer"
    dimmer.model = MODEL
    dimmer.host = IP_ADDRESS
    dimmer.brightness = 50
    dimmer.color_temp = 4000
    dimmer.is_color = True
    dimmer.is_strip = False
    dimmer.is_plug = False
    dimmer.is_dimmer = True
    dimmer.is_light_strip = False
    dimmer.effect = None
    dimmer.effect_list = None
    dimmer.hsv = (10, 30, 5)
    dimmer.device_id = MAC_ADDRESS
    dimmer.valid_temperature_range.min = 4000
    dimmer.valid_temperature_range.max = 9000
    dimmer.hw_info = {"sw_ver": "1.0.0", "hw_ver": "1.0.0"}
    dimmer.turn_off = AsyncMock()
    dimmer.turn_on = AsyncMock()
    dimmer.set_brightness = AsyncMock()
    dimmer.set_hsv = AsyncMock()
    dimmer.set_color_temp = AsyncMock()
    dimmer.set_led = AsyncMock()
    dimmer.protocol = _mock_protocol()
    return dimmer


def _mocked_plug() -> SmartPlug:
    plug = MagicMock(auto_spec=SmartPlug, name="Mocked plug")
    plug.update = AsyncMock()
    plug.mac = MAC_ADDRESS
    plug.alias = "My Plug"
    plug.model = MODEL
    plug.host = IP_ADDRESS
    plug.is_light_strip = False
    plug.is_bulb = False
    plug.is_dimmer = False
    plug.is_strip = False
    plug.is_plug = True
    plug.device_id = MAC_ADDRESS
    plug.hw_info = {"sw_ver": "1.0.0", "hw_ver": "1.0.0"}
    plug.turn_off = AsyncMock()
    plug.turn_on = AsyncMock()
    plug.set_led = AsyncMock()
    plug.protocol = _mock_protocol()
    return plug


def _mocked_strip() -> SmartStrip:
    strip = MagicMock(auto_spec=SmartStrip, name="Mocked strip")
    strip.update = AsyncMock()
    strip.mac = MAC_ADDRESS
    strip.alias = "My Strip"
    strip.model = MODEL
    strip.host = IP_ADDRESS
    strip.is_light_strip = False
    strip.is_bulb = False
    strip.is_dimmer = False
    strip.is_strip = True
    strip.is_plug = True
    strip.device_id = MAC_ADDRESS
    strip.hw_info = {"sw_ver": "1.0.0", "hw_ver": "1.0.0"}
    strip.turn_off = AsyncMock()
    strip.turn_on = AsyncMock()
    strip.set_led = AsyncMock()
    strip.protocol = _mock_protocol()
    plug0 = _mocked_plug()
    plug0.alias = "Plug0"
    plug0.device_id = "bb:bb:cc:dd:ee:ff_PLUG0DEVICEID"
    plug0.mac = "bb:bb:cc:dd:ee:ff"
    plug0.protocol = _mock_protocol()
    plug1 = _mocked_plug()
    plug1.device_id = "cc:bb:cc:dd:ee:ff_PLUG1DEVICEID"
    plug1.mac = "cc:bb:cc:dd:ee:ff"
    plug1.alias = "Plug1"
    plug1.protocol = _mock_protocol()
    strip.children = [plug0, plug1]
    return strip


def _patch_discovery(device=None, no_device=False):
    async def _discovery(*args, **kwargs):
        if no_device:
            return {}
        return {IP_ADDRESS: _mocked_bulb()}

    return patch("homeassistant.components.tplink.Discover.discover", new=_discovery)


def _patch_single_discovery(device=None, no_device=False):
    async def _discover_single(*_):
        if no_device:
            raise SmartDeviceException
        return device if device else _mocked_bulb()

    return patch(
        "homeassistant.components.tplink.Discover.discover_single", new=_discover_single
    )


async def initialize_config_entry_for_device(
    hass: HomeAssistant, dev: SmartDevice
) -> MockConfigEntry:
    """Create a mocked configuration entry for the given device.

    Note, the rest of the tests should probably be converted over to use this
    instead of repeating the initialization routine for each test separately
    """
    config_entry = MockConfigEntry(
        title="TP-Link", domain=DOMAIN, unique_id=dev.mac, data={CONF_HOST: dev.host}
    )
    config_entry.add_to_hass(hass)

    with _patch_discovery(device=dev), _patch_single_discovery(device=dev):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    return config_entry
