"""Test MQTT diagnostics."""

import json
from unittest.mock import ANY

import pytest

from homeassistant.components import mqtt

from tests.common import async_fire_mqtt_message, mock_device_registry
from tests.components.diagnostics import (
    get_diagnostics_for_config_entry,
    get_diagnostics_for_device,
)

default_config = {
    "birth_message": {},
    "broker": "mock-broker",
    "discovery": True,
    "discovery_prefix": "homeassistant",
    "keepalive": 60,
    "port": 1883,
    "protocol": "3.1.1",
    "tls_version": "auto",
    "will_message": {
        "payload": "offline",
        "qos": 0,
        "retain": False,
        "topic": "homeassistant/status",
    },
}


@pytest.fixture
def device_reg(hass):
    """Return an empty, loaded, registry."""
    return mock_device_registry(hass)


async def test_entry_diagnostics(hass, device_reg, hass_client, mqtt_mock):
    """Test config entry diagnostics."""
    config_entry = hass.config_entries.async_entries(mqtt.DOMAIN)[0]
    mqtt_mock.connected = True

    assert await get_diagnostics_for_config_entry(hass, hass_client, config_entry) == {
        "connected": True,
        "devices": [],
        "mqtt_config": default_config,
        "mqtt_debug_info": {"entities": [], "triggers": []},
    }

    # Discover a device with an entity and a trigger
    config_sensor = {
        "device": {"identifiers": ["0AFFD2"]},
        "platform": "mqtt",
        "state_topic": "foobar/sensor",
        "unique_id": "unique",
    }
    config_trigger = {
        "automation_type": "trigger",
        "device": {"identifiers": ["0AFFD2"]},
        "platform": "mqtt",
        "topic": "test-topic1",
        "type": "foo",
        "subtype": "bar",
    }
    data_sensor = json.dumps(config_sensor)
    data_trigger = json.dumps(config_trigger)

    async_fire_mqtt_message(hass, "homeassistant/sensor/bla/config", data_sensor)
    async_fire_mqtt_message(
        hass, "homeassistant/device_automation/bla/config", data_trigger
    )
    await hass.async_block_till_done()

    device_entry = device_reg.async_get_device({("mqtt", "0AFFD2")})

    expected_debug_info = {
        "entities": [
            {
                "entity_id": "sensor.mqtt_sensor",
                "subscriptions": [{"topic": "foobar/sensor", "messages": []}],
                "discovery_data": {
                    "payload": config_sensor,
                    "topic": "homeassistant/sensor/bla/config",
                },
                "transmitted": [],
            }
        ],
        "triggers": [
            {
                "discovery_data": {
                    "payload": config_trigger,
                    "topic": "homeassistant/device_automation/bla/config",
                },
                "trigger_key": ["device_automation", "bla"],
            }
        ],
    }

    expected_device = {
        "disabled": False,
        "disabled_by": None,
        "entities": [
            {
                "device_class": None,
                "disabled": False,
                "disabled_by": None,
                "entity_category": None,
                "entity_id": "sensor.mqtt_sensor",
                "icon": None,
                "original_device_class": None,
                "original_icon": None,
                "state": {
                    "attributes": {"friendly_name": "MQTT Sensor"},
                    "entity_id": "sensor.mqtt_sensor",
                    "last_changed": ANY,
                    "last_updated": ANY,
                    "state": "unknown",
                },
                "unit_of_measurement": None,
            }
        ],
        "id": device_entry.id,
        "name": None,
        "name_by_user": None,
    }

    assert await get_diagnostics_for_config_entry(hass, hass_client, config_entry) == {
        "connected": True,
        "devices": [expected_device],
        "mqtt_config": default_config,
        "mqtt_debug_info": expected_debug_info,
    }

    assert await get_diagnostics_for_device(
        hass, hass_client, config_entry, device_entry
    ) == {
        "connected": True,
        "device": expected_device,
        "mqtt_config": default_config,
        "mqtt_debug_info": expected_debug_info,
    }


@pytest.mark.parametrize(
    "mqtt_config",
    [
        {
            mqtt.CONF_BROKER: "mock-broker",
            mqtt.CONF_BIRTH_MESSAGE: {},
            mqtt.CONF_PASSWORD: "hunter2",
            mqtt.CONF_USERNAME: "my_user",
        }
    ],
)
async def test_redact_diagnostics(hass, device_reg, hass_client, mqtt_mock):
    """Test redacting diagnostics."""
    expected_config = dict(default_config)
    expected_config["password"] = "**REDACTED**"
    expected_config["username"] = "**REDACTED**"

    config_entry = hass.config_entries.async_entries(mqtt.DOMAIN)[0]
    mqtt_mock.connected = True

    # Discover a device with a device tracker
    config_tracker = {
        "device": {"identifiers": ["0AFFD2"]},
        "platform": "mqtt",
        "state_topic": "foobar/device_tracker",
        "json_attributes_topic": "attributes-topic",
        "unique_id": "unique",
    }
    data_tracker = json.dumps(config_tracker)

    async_fire_mqtt_message(
        hass, "homeassistant/device_tracker/bla/config", data_tracker
    )
    await hass.async_block_till_done()

    location_data = '{"latitude":32.87336,"longitude": -117.22743, "gps_accuracy":1.5}'
    async_fire_mqtt_message(hass, "attributes-topic", location_data)
    await hass.async_block_till_done()

    device_entry = device_reg.async_get_device({("mqtt", "0AFFD2")})

    expected_debug_info = {
        "entities": [
            {
                "entity_id": "device_tracker.mqtt_unique",
                "subscriptions": [
                    {
                        "topic": "attributes-topic",
                        "messages": [
                            {
                                "payload": location_data,
                                "qos": 0,
                                "retain": False,
                                "time": ANY,
                                "topic": "attributes-topic",
                            }
                        ],
                    },
                    {"topic": "foobar/device_tracker", "messages": []},
                ],
                "discovery_data": {
                    "payload": config_tracker,
                    "topic": "homeassistant/device_tracker/bla/config",
                },
                "transmitted": [],
            }
        ],
        "triggers": [],
    }

    expected_device = {
        "disabled": False,
        "disabled_by": None,
        "entities": [
            {
                "device_class": None,
                "disabled": False,
                "disabled_by": None,
                "entity_category": None,
                "entity_id": "device_tracker.mqtt_unique",
                "icon": None,
                "original_device_class": None,
                "original_icon": None,
                "state": {
                    "attributes": {
                        "gps_accuracy": 1.5,
                        "latitude": "**REDACTED**",
                        "longitude": "**REDACTED**",
                        "source_type": None,
                    },
                    "entity_id": "device_tracker.mqtt_unique",
                    "last_changed": ANY,
                    "last_updated": ANY,
                    "state": "home",
                },
                "unit_of_measurement": None,
            }
        ],
        "id": device_entry.id,
        "name": None,
        "name_by_user": None,
    }

    assert await get_diagnostics_for_config_entry(hass, hass_client, config_entry) == {
        "connected": True,
        "devices": [expected_device],
        "mqtt_config": expected_config,
        "mqtt_debug_info": expected_debug_info,
    }

    assert await get_diagnostics_for_device(
        hass, hass_client, config_entry, device_entry
    ) == {
        "connected": True,
        "device": expected_device,
        "mqtt_config": expected_config,
        "mqtt_debug_info": expected_debug_info,
    }
