"""The tests for the Mikrotik device tracker platform."""
from datetime import timedelta

import pytest

from homeassistant.components import mikrotik
import homeassistant.components.device_tracker as device_tracker
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
import homeassistant.util.dt as dt_util

from . import DEVICE_2_WIRELESS, DHCP_DATA, MOCK_DATA, MOCK_OPTIONS, WIRELESS_DATA
from .test_hub import setup_mikrotik_entry

from tests.common import MockConfigEntry, patch

DEFAULT_DETECTION_TIME = timedelta(seconds=300)


@pytest.fixture
def mock_device_registry_devices(hass):
    """Create device registry devices so the device tracker entities are enabled."""
    dev_reg = dr.async_get(hass)
    config_entry = MockConfigEntry(domain="something_else")

    for idx, device in enumerate(
        (
            "00:00:00:00:00:01",
            "00:00:00:00:00:02",
        )
    ):
        dev_reg.async_get_or_create(
            name=f"Device {idx}",
            config_entry_id=config_entry.entry_id,
            connections={(dr.CONNECTION_NETWORK_MAC, device)},
        )


def mock_command(self, cmd, params=None):
    """Mock the Mikrotik command method."""
    if cmd == mikrotik.const.MIKROTIK_SERVICES[mikrotik.const.IS_WIRELESS]:
        return True
    if cmd == mikrotik.const.MIKROTIK_SERVICES[mikrotik.const.DHCP]:
        return DHCP_DATA
    if cmd == mikrotik.const.MIKROTIK_SERVICES[mikrotik.const.WIRELESS]:
        return WIRELESS_DATA
    return {}


async def test_platform_manually_configured(hass):
    """Test that nothing happens when configuring mikrotik through device tracker platform."""
    assert (
        await async_setup_component(
            hass,
            device_tracker.DOMAIN,
            {device_tracker.DOMAIN: {"platform": "mikrotik"}},
        )
        is False
    )
    assert mikrotik.DOMAIN not in hass.data


async def test_device_trackers(hass, mock_device_registry_devices):
    """Test device_trackers created by mikrotik."""

    # test devices are added from wireless list only
    hub = await setup_mikrotik_entry(hass)

    device_1 = hass.states.get("device_tracker.device_1")
    assert device_1 is not None
    assert device_1.state == "home"
    assert device_1.attributes["ip"] == "0.0.0.1"
    assert "ip_address" not in device_1.attributes
    assert device_1.attributes["mac"] == "00:00:00:00:00:01"
    assert device_1.attributes["host_name"] == "Device_1"
    assert "mac_address" not in device_1.attributes
    device_2 = hass.states.get("device_tracker.device_2")
    assert device_2 is None

    with patch.object(mikrotik.hub.MikrotikData, "command", new=mock_command):
        # test device_2 is added after connecting to wireless network
        WIRELESS_DATA.append(DEVICE_2_WIRELESS)

        await hub.async_update()
        await hass.async_block_till_done()

        device_2 = hass.states.get("device_tracker.device_2")
        assert device_2 is not None
        assert device_2.state == "home"
        assert device_2.attributes["ip"] == "0.0.0.2"
        assert "ip_address" not in device_2.attributes
        assert device_2.attributes["mac"] == "00:00:00:00:00:02"
        assert "mac_address" not in device_2.attributes
        assert device_2.attributes["host_name"] == "Device_2"

        # test state remains home if last_seen  consider_home_interval
        del WIRELESS_DATA[1]  # device 2 is removed from wireless list
        hub.api.devices["00:00:00:00:00:02"]._last_seen = dt_util.utcnow() - timedelta(
            minutes=4
        )
        await hub.async_update()
        await hass.async_block_till_done()

        device_2 = hass.states.get("device_tracker.device_2")
        assert device_2.state != "not_home"

        # test state changes to away if last_seen > consider_home_interval
        hub.api.devices["00:00:00:00:00:02"]._last_seen = dt_util.utcnow() - timedelta(
            minutes=5
        )
        await hub.async_update()
        await hass.async_block_till_done()

        device_2 = hass.states.get("device_tracker.device_2")
        assert device_2.state == "not_home"


async def test_restoring_devices(hass):
    """Test restoring existing device_tracker entities if not detected on startup."""
    config_entry = MockConfigEntry(
        domain=mikrotik.DOMAIN, data=MOCK_DATA, options=MOCK_OPTIONS
    )
    config_entry.add_to_hass(hass)

    registry = er.async_get(hass)
    registry.async_get_or_create(
        device_tracker.DOMAIN,
        mikrotik.DOMAIN,
        "00:00:00:00:00:01",
        suggested_object_id="device_1",
        config_entry=config_entry,
    )
    registry.async_get_or_create(
        device_tracker.DOMAIN,
        mikrotik.DOMAIN,
        "00:00:00:00:00:02",
        suggested_object_id="device_2",
        config_entry=config_entry,
    )

    await setup_mikrotik_entry(hass)

    # test device_2 which is not in wireless list is restored
    device_1 = hass.states.get("device_tracker.device_1")
    assert device_1 is not None
    assert device_1.state == "home"
    device_2 = hass.states.get("device_tracker.device_2")
    assert device_2 is not None
    assert device_2.state == "not_home"
