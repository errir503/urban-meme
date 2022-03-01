"""The tests for the Tasmota binary sensor platform."""
import copy
import json
from unittest.mock import call

from homeassistant.components.tasmota.const import DEFAULT_PREFIX, DOMAIN
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component

from .test_common import DEFAULT_CONFIG

from tests.common import MockConfigEntry, async_fire_mqtt_message


async def test_device_remove(
    hass, mqtt_mock, caplog, device_reg, entity_reg, setup_tasmota
):
    """Test removing a discovered device through device registry."""
    config = copy.deepcopy(DEFAULT_CONFIG)
    mac = config["mac"]

    async_fire_mqtt_message(hass, f"{DEFAULT_PREFIX}/{mac}/config", json.dumps(config))
    await hass.async_block_till_done()

    # Verify device entry is created
    device_entry = device_reg.async_get_device(
        set(), {(dr.CONNECTION_NETWORK_MAC, mac)}
    )
    assert device_entry is not None

    device_reg.async_remove_device(device_entry.id)
    await hass.async_block_till_done()

    # Verify device entry is removed
    device_entry = device_reg.async_get_device(
        set(), {(dr.CONNECTION_NETWORK_MAC, mac)}
    )
    assert device_entry is None

    # Verify retained discovery topic has been cleared
    mqtt_mock.async_publish.assert_has_calls(
        [
            call(f"tasmota/discovery/{mac}/config", "", 0, True),
            call(f"tasmota/discovery/{mac}/sensors", "", 0, True),
        ],
        any_order=True,
    )


async def test_device_remove_non_tasmota_device(
    hass, device_reg, hass_ws_client, mqtt_mock, setup_tasmota
):
    """Test removing a non Tasmota device through device registry."""
    config_entry = MockConfigEntry(domain="test")
    config_entry.add_to_hass(hass)

    mac = "12:34:56:AB:CD:EF"
    device_entry = device_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, mac)},
    )
    assert device_entry is not None

    device_reg.async_remove_device(device_entry.id)
    await hass.async_block_till_done()

    # Verify device entry is removed
    device_entry = device_reg.async_get_device(
        set(), {(dr.CONNECTION_NETWORK_MAC, mac)}
    )
    assert device_entry is None

    # Verify no Tasmota discovery message was sent
    mqtt_mock.async_publish.assert_not_called()


async def test_device_remove_stale_tasmota_device(
    hass, device_reg, hass_ws_client, mqtt_mock, setup_tasmota
):
    """Test removing a stale (undiscovered) Tasmota device through device registry."""
    config_entry = hass.config_entries.async_entries("tasmota")[0]

    mac = "12:34:56:AB:CD:EF"
    device_entry = device_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, mac)},
    )
    assert device_entry is not None

    device_reg.async_remove_device(device_entry.id)
    await hass.async_block_till_done()

    # Verify device entry is removed
    device_entry = device_reg.async_get_device(
        set(), {(dr.CONNECTION_NETWORK_MAC, mac)}
    )
    assert device_entry is None

    # Verify retained discovery topic has been cleared
    mac = mac.replace(":", "")
    mqtt_mock.async_publish.assert_has_calls(
        [
            call(f"tasmota/discovery/{mac}/config", "", 0, True),
            call(f"tasmota/discovery/{mac}/sensors", "", 0, True),
        ],
        any_order=True,
    )


async def test_tasmota_ws_remove_discovered_device(
    hass, device_reg, entity_reg, hass_ws_client, mqtt_mock, setup_tasmota
):
    """Test Tasmota websocket device removal."""
    assert await async_setup_component(hass, "config", {})
    config = copy.deepcopy(DEFAULT_CONFIG)
    mac = config["mac"]

    async_fire_mqtt_message(hass, f"{DEFAULT_PREFIX}/{mac}/config", json.dumps(config))
    await hass.async_block_till_done()

    # Verify device entry is created
    device_entry = device_reg.async_get_device(
        set(), {(dr.CONNECTION_NETWORK_MAC, mac)}
    )
    assert device_entry is not None

    client = await hass_ws_client(hass)
    tasmota_config_entry = hass.config_entries.async_entries(DOMAIN)[0]
    await client.send_json(
        {
            "id": 5,
            "config_entry_id": tasmota_config_entry.entry_id,
            "type": "config/device_registry/remove_config_entry",
            "device_id": device_entry.id,
        }
    )
    response = await client.receive_json()
    assert response["success"]

    # Verify device entry is cleared
    device_entry = device_reg.async_get_device(
        set(), {(dr.CONNECTION_NETWORK_MAC, mac)}
    )
    assert device_entry is None
