"""The tests for the MQTT discovery."""
import json
from pathlib import Path
import re
from unittest.mock import AsyncMock, call, patch

import pytest

from homeassistant import config_entries
from homeassistant.components import mqtt
from homeassistant.components.mqtt.abbreviations import (
    ABBREVIATIONS,
    DEVICE_ABBREVIATIONS,
)
from homeassistant.components.mqtt.discovery import ALREADY_DISCOVERED, async_start
from homeassistant.const import (
    EVENT_STATE_CHANGED,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
import homeassistant.core as ha
from homeassistant.setup import async_setup_component

from tests.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
    mock_device_registry,
    mock_entity_platform,
    mock_registry,
)


@pytest.fixture
def device_reg(hass):
    """Return an empty, loaded, registry."""
    return mock_device_registry(hass)


@pytest.fixture
def entity_reg(hass):
    """Return an empty, loaded, registry."""
    return mock_registry(hass)


@pytest.mark.parametrize(
    "mqtt_config",
    [{mqtt.CONF_BROKER: "mock-broker", mqtt.CONF_DISCOVERY: False}],
)
async def test_subscribing_config_topic(hass, mqtt_mock):
    """Test setting up discovery."""
    entry = hass.config_entries.async_entries(mqtt.DOMAIN)[0]

    discovery_topic = "homeassistant"
    await async_start(hass, discovery_topic, entry)

    call_args1 = mqtt_mock.async_subscribe.mock_calls[0][1]
    assert call_args1[2] == 0
    call_args2 = mqtt_mock.async_subscribe.mock_calls[1][1]
    assert call_args2[2] == 0
    topics = [call_args1[0], call_args2[0]]
    assert discovery_topic + "/+/+/config" in topics
    assert discovery_topic + "/+/+/+/config" in topics


@pytest.mark.parametrize(
    "topic, log",
    [
        ("homeassistant/binary_sensor/bla/not_config", False),
        ("homeassistant/binary_sensor/rörkrökare/config", True),
    ],
)
async def test_invalid_topic(hass, mqtt_mock, caplog, topic, log):
    """Test sending to invalid topic."""
    with patch(
        "homeassistant.components.mqtt.discovery.async_dispatcher_send"
    ) as mock_dispatcher_send:
        mock_dispatcher_send = AsyncMock(return_value=None)

        async_fire_mqtt_message(hass, topic, "{}")
        await hass.async_block_till_done()
        assert not mock_dispatcher_send.called
        if log:
            assert (
                f"Received message on illegal discovery topic '{topic}'" in caplog.text
            )
        else:
            assert "Received message on illegal discovery topic'" not in caplog.text
        caplog.clear()


async def test_invalid_json(hass, mqtt_mock, caplog):
    """Test sending in invalid JSON."""
    with patch(
        "homeassistant.components.mqtt.discovery.async_dispatcher_send"
    ) as mock_dispatcher_send:

        mock_dispatcher_send = AsyncMock(return_value=None)

        async_fire_mqtt_message(
            hass, "homeassistant/binary_sensor/bla/config", "not json"
        )
        await hass.async_block_till_done()
        assert "Unable to parse JSON" in caplog.text
        assert not mock_dispatcher_send.called


async def test_only_valid_components(hass, mqtt_mock, caplog):
    """Test for a valid component."""
    with patch(
        "homeassistant.components.mqtt.discovery.async_dispatcher_send"
    ) as mock_dispatcher_send:

        invalid_component = "timer"

        mock_dispatcher_send = AsyncMock(return_value=None)

        async_fire_mqtt_message(
            hass, f"homeassistant/{invalid_component}/bla/config", "{}"
        )

    await hass.async_block_till_done()

    assert f"Integration {invalid_component} is not supported" in caplog.text

    assert not mock_dispatcher_send.called


async def test_correct_config_discovery(hass, mqtt_mock, caplog):
    """Test sending in correct JSON."""
    async_fire_mqtt_message(
        hass,
        "homeassistant/binary_sensor/bla/config",
        '{ "name": "Beer", "state_topic": "test-topic" }',
    )
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.beer")

    assert state is not None
    assert state.name == "Beer"
    assert ("binary_sensor", "bla") in hass.data[ALREADY_DISCOVERED]


async def test_discover_fan(hass, mqtt_mock, caplog):
    """Test discovering an MQTT fan."""
    async_fire_mqtt_message(
        hass,
        "homeassistant/fan/bla/config",
        ('{ "name": "Beer",' '  "command_topic": "test_topic" }'),
    )
    await hass.async_block_till_done()

    state = hass.states.get("fan.beer")

    assert state is not None
    assert state.name == "Beer"
    assert ("fan", "bla") in hass.data[ALREADY_DISCOVERED]


async def test_discover_climate(hass, mqtt_mock, caplog):
    """Test discovering an MQTT climate component."""
    data = (
        '{ "name": "ClimateTest",'
        '  "current_temperature_topic": "climate/bla/current_temp",'
        '  "temperature_command_topic": "climate/bla/target_temp" }'
    )

    async_fire_mqtt_message(hass, "homeassistant/climate/bla/config", data)
    await hass.async_block_till_done()

    state = hass.states.get("climate.ClimateTest")

    assert state is not None
    assert state.name == "ClimateTest"
    assert ("climate", "bla") in hass.data[ALREADY_DISCOVERED]


async def test_discover_alarm_control_panel(hass, mqtt_mock, caplog):
    """Test discovering an MQTT alarm control panel component."""
    data = (
        '{ "name": "AlarmControlPanelTest",'
        '  "state_topic": "test_topic",'
        '  "command_topic": "test_topic" }'
    )

    async_fire_mqtt_message(hass, "homeassistant/alarm_control_panel/bla/config", data)
    await hass.async_block_till_done()

    state = hass.states.get("alarm_control_panel.AlarmControlPanelTest")

    assert state is not None
    assert state.name == "AlarmControlPanelTest"
    assert ("alarm_control_panel", "bla") in hass.data[ALREADY_DISCOVERED]


@pytest.mark.parametrize(
    "topic, config, entity_id, name, domain",
    [
        (
            "homeassistant/alarm_control_panel/object/bla/config",
            '{ "name": "Hello World 1", "obj_id": "hello_id", "state_topic": "test-topic", "command_topic": "test-topic" }',
            "alarm_control_panel.hello_id",
            "Hello World 1",
            "alarm_control_panel",
        ),
        (
            "homeassistant/binary_sensor/object/bla/config",
            '{ "name": "Hello World 2", "obj_id": "hello_id", "state_topic": "test-topic" }',
            "binary_sensor.hello_id",
            "Hello World 2",
            "binary_sensor",
        ),
        (
            "homeassistant/button/object/bla/config",
            '{ "name": "Hello World button", "obj_id": "hello_id", "command_topic": "test-topic" }',
            "button.hello_id",
            "Hello World button",
            "button",
        ),
        (
            "homeassistant/camera/object/bla/config",
            '{ "name": "Hello World 3", "obj_id": "hello_id", "state_topic": "test-topic", "topic": "test-topic" }',
            "camera.hello_id",
            "Hello World 3",
            "camera",
        ),
        (
            "homeassistant/climate/object/bla/config",
            '{ "name": "Hello World 4", "obj_id": "hello_id", "state_topic": "test-topic" }',
            "climate.hello_id",
            "Hello World 4",
            "climate",
        ),
        (
            "homeassistant/cover/object/bla/config",
            '{ "name": "Hello World 5", "obj_id": "hello_id", "state_topic": "test-topic" }',
            "cover.hello_id",
            "Hello World 5",
            "cover",
        ),
        (
            "homeassistant/fan/object/bla/config",
            '{ "name": "Hello World 6", "obj_id": "hello_id", "state_topic": "test-topic", "command_topic": "test-topic" }',
            "fan.hello_id",
            "Hello World 6",
            "fan",
        ),
        (
            "homeassistant/humidifier/object/bla/config",
            '{ "name": "Hello World 7", "obj_id": "hello_id", "state_topic": "test-topic", "target_humidity_command_topic": "test-topic", "command_topic": "test-topic" }',
            "humidifier.hello_id",
            "Hello World 7",
            "humidifier",
        ),
        (
            "homeassistant/number/object/bla/config",
            '{ "name": "Hello World 8", "obj_id": "hello_id", "state_topic": "test-topic", "command_topic": "test-topic" }',
            "number.hello_id",
            "Hello World 8",
            "number",
        ),
        (
            "homeassistant/scene/object/bla/config",
            '{ "name": "Hello World 9", "obj_id": "hello_id", "state_topic": "test-topic", "command_topic": "test-topic" }',
            "scene.hello_id",
            "Hello World 9",
            "scene",
        ),
        (
            "homeassistant/select/object/bla/config",
            '{ "name": "Hello World 10", "obj_id": "hello_id", "state_topic": "test-topic", "options": [ "opt1", "opt2" ], "command_topic": "test-topic" }',
            "select.hello_id",
            "Hello World 10",
            "select",
        ),
        (
            "homeassistant/sensor/object/bla/config",
            '{ "name": "Hello World 11", "obj_id": "hello_id", "state_topic": "test-topic" }',
            "sensor.hello_id",
            "Hello World 11",
            "sensor",
        ),
        (
            "homeassistant/switch/object/bla/config",
            '{ "name": "Hello World 12", "obj_id": "hello_id", "state_topic": "test-topic", "command_topic": "test-topic" }',
            "switch.hello_id",
            "Hello World 12",
            "switch",
        ),
        (
            "homeassistant/light/object/bla/config",
            '{ "name": "Hello World 13", "obj_id": "hello_id", "state_topic": "test-topic", "command_topic": "test-topic" }',
            "light.hello_id",
            "Hello World 13",
            "light",
        ),
        (
            "homeassistant/light/object/bla/config",
            '{ "name": "Hello World 14", "obj_id": "hello_id", "state_topic": "test-topic", "command_topic": "test-topic", "schema": "json" }',
            "light.hello_id",
            "Hello World 14",
            "light",
        ),
        (
            "homeassistant/light/object/bla/config",
            '{ "name": "Hello World 15", "obj_id": "hello_id", "state_topic": "test-topic", "command_off_template": "template", "command_on_template": "template", "command_topic": "test-topic", "schema": "template" }',
            "light.hello_id",
            "Hello World 15",
            "light",
        ),
        (
            "homeassistant/vacuum/object/bla/config",
            '{ "name": "Hello World 16", "obj_id": "hello_id", "state_topic": "test-topic", "schema": "state" }',
            "vacuum.hello_id",
            "Hello World 16",
            "vacuum",
        ),
        (
            "homeassistant/vacuum/object/bla/config",
            '{ "name": "Hello World 17", "obj_id": "hello_id", "state_topic": "test-topic", "schema": "legacy" }',
            "vacuum.hello_id",
            "Hello World 17",
            "vacuum",
        ),
        (
            "homeassistant/lock/object/bla/config",
            '{ "name": "Hello World 18", "obj_id": "hello_id", "state_topic": "test-topic", "command_topic": "test-topic" }',
            "lock.hello_id",
            "Hello World 18",
            "lock",
        ),
        (
            "homeassistant/device_tracker/object/bla/config",
            '{ "name": "Hello World 19", "obj_id": "hello_id", "state_topic": "test-topic" }',
            "device_tracker.hello_id",
            "Hello World 19",
            "device_tracker",
        ),
    ],
)
async def test_discovery_with_object_id(
    hass, mqtt_mock, caplog, topic, config, entity_id, name, domain
):
    """Test discovering an MQTT entity with object_id."""
    async_fire_mqtt_message(hass, topic, config)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)

    assert state is not None
    assert state.name == name
    assert (domain, "object bla") in hass.data[ALREADY_DISCOVERED]


async def test_discovery_incl_nodeid(hass, mqtt_mock, caplog):
    """Test sending in correct JSON with optional node_id included."""
    async_fire_mqtt_message(
        hass,
        "homeassistant/binary_sensor/my_node_id/bla/config",
        '{ "name": "Beer", "state_topic": "test-topic" }',
    )
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.beer")

    assert state is not None
    assert state.name == "Beer"
    assert ("binary_sensor", "my_node_id bla") in hass.data[ALREADY_DISCOVERED]


async def test_non_duplicate_discovery(hass, mqtt_mock, caplog):
    """Test for a non duplicate component."""
    async_fire_mqtt_message(
        hass,
        "homeassistant/binary_sensor/bla/config",
        '{ "name": "Beer", "state_topic": "test-topic" }',
    )
    async_fire_mqtt_message(
        hass,
        "homeassistant/binary_sensor/bla/config",
        '{ "name": "Beer", "state_topic": "test-topic" }',
    )
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.beer")
    state_duplicate = hass.states.get("binary_sensor.beer1")

    assert state is not None
    assert state.name == "Beer"
    assert state_duplicate is None
    assert "Component has already been discovered: binary_sensor bla" in caplog.text


async def test_removal(hass, mqtt_mock, caplog):
    """Test removal of component through empty discovery message."""
    async_fire_mqtt_message(
        hass,
        "homeassistant/binary_sensor/bla/config",
        '{ "name": "Beer", "state_topic": "test-topic" }',
    )
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.beer")
    assert state is not None

    async_fire_mqtt_message(hass, "homeassistant/binary_sensor/bla/config", "")
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.beer")
    assert state is None


async def test_rediscover(hass, mqtt_mock, caplog):
    """Test rediscover of removed component."""
    async_fire_mqtt_message(
        hass,
        "homeassistant/binary_sensor/bla/config",
        '{ "name": "Beer", "state_topic": "test-topic" }',
    )
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.beer")
    assert state is not None

    async_fire_mqtt_message(hass, "homeassistant/binary_sensor/bla/config", "")
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.beer")
    assert state is None

    async_fire_mqtt_message(
        hass,
        "homeassistant/binary_sensor/bla/config",
        '{ "name": "Beer", "state_topic": "test-topic" }',
    )
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.beer")
    assert state is not None


async def test_rapid_rediscover(hass, mqtt_mock, caplog):
    """Test immediate rediscover of removed component."""

    events = []

    @ha.callback
    def callback(event):
        """Verify event got called."""
        events.append(event)

    hass.bus.async_listen(EVENT_STATE_CHANGED, callback)

    async_fire_mqtt_message(
        hass,
        "homeassistant/binary_sensor/bla/config",
        '{ "name": "Beer", "state_topic": "test-topic" }',
    )
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.beer")
    assert state is not None
    assert len(events) == 1

    # Removal immediately followed by rediscover
    async_fire_mqtt_message(hass, "homeassistant/binary_sensor/bla/config", "")
    async_fire_mqtt_message(
        hass,
        "homeassistant/binary_sensor/bla/config",
        '{ "name": "Beer", "state_topic": "test-topic" }',
    )
    async_fire_mqtt_message(hass, "homeassistant/binary_sensor/bla/config", "")
    async_fire_mqtt_message(
        hass,
        "homeassistant/binary_sensor/bla/config",
        '{ "name": "Milk", "state_topic": "test-topic" }',
    )
    await hass.async_block_till_done()

    assert len(hass.states.async_entity_ids("binary_sensor")) == 1
    state = hass.states.get("binary_sensor.milk")
    assert state is not None

    assert len(events) == 5
    # Remove the entity
    assert events[1].data["entity_id"] == "binary_sensor.beer"
    assert events[1].data["new_state"] is None
    # Add the entity
    assert events[2].data["entity_id"] == "binary_sensor.beer"
    assert events[2].data["old_state"] is None
    # Remove the entity
    assert events[3].data["entity_id"] == "binary_sensor.beer"
    assert events[3].data["new_state"] is None
    # Add the entity
    assert events[4].data["entity_id"] == "binary_sensor.milk"
    assert events[4].data["old_state"] is None


async def test_rapid_rediscover_unique(hass, mqtt_mock, caplog):
    """Test immediate rediscover of removed component."""

    events = []

    @ha.callback
    def callback(event):
        """Verify event got called."""
        events.append(event)

    hass.bus.async_listen(EVENT_STATE_CHANGED, callback)

    async_fire_mqtt_message(
        hass,
        "homeassistant/binary_sensor/bla2/config",
        '{ "name": "Ale", "state_topic": "test-topic", "unique_id": "very_unique" }',
    )
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.ale")
    assert state is not None
    assert len(events) == 1

    # Duplicate unique_id, immediately followed by correct unique_id
    async_fire_mqtt_message(
        hass,
        "homeassistant/binary_sensor/bla/config",
        '{ "name": "Beer", "state_topic": "test-topic", "unique_id": "very_unique" }',
    )
    async_fire_mqtt_message(
        hass,
        "homeassistant/binary_sensor/bla/config",
        '{ "name": "Beer", "state_topic": "test-topic", "unique_id": "even_uniquer" }',
    )
    async_fire_mqtt_message(hass, "homeassistant/binary_sensor/bla/config", "")
    async_fire_mqtt_message(
        hass,
        "homeassistant/binary_sensor/bla/config",
        '{ "name": "Milk", "state_topic": "test-topic", "unique_id": "even_uniquer" }',
    )
    await hass.async_block_till_done()

    assert len(hass.states.async_entity_ids("binary_sensor")) == 2
    state = hass.states.get("binary_sensor.ale")
    assert state is not None
    state = hass.states.get("binary_sensor.milk")
    assert state is not None

    assert len(events) == 4
    # Add the entity
    assert events[1].data["entity_id"] == "binary_sensor.beer"
    assert events[1].data["old_state"] is None
    # Remove the entity
    assert events[2].data["entity_id"] == "binary_sensor.beer"
    assert events[2].data["new_state"] is None
    # Add the entity
    assert events[3].data["entity_id"] == "binary_sensor.milk"
    assert events[3].data["old_state"] is None


async def test_duplicate_removal(hass, mqtt_mock, caplog):
    """Test for a non duplicate component."""
    async_fire_mqtt_message(
        hass,
        "homeassistant/binary_sensor/bla/config",
        '{ "name": "Beer", "state_topic": "test-topic" }',
    )
    await hass.async_block_till_done()
    async_fire_mqtt_message(hass, "homeassistant/binary_sensor/bla/config", "")
    await hass.async_block_till_done()
    assert "Component has already been discovered: binary_sensor bla" in caplog.text
    caplog.clear()
    async_fire_mqtt_message(hass, "homeassistant/binary_sensor/bla/config", "")
    await hass.async_block_till_done()

    assert "Component has already been discovered: binary_sensor bla" not in caplog.text


async def test_cleanup_device(hass, hass_ws_client, device_reg, entity_reg, mqtt_mock):
    """Test discvered device is cleaned up when entry removed from device."""
    assert await async_setup_component(hass, "config", {})
    ws_client = await hass_ws_client(hass)

    data = (
        '{ "device":{"identifiers":["0AFFD2"]},'
        '  "state_topic": "foobar/sensor",'
        '  "unique_id": "unique" }'
    )

    async_fire_mqtt_message(hass, "homeassistant/sensor/bla/config", data)
    await hass.async_block_till_done()

    # Verify device and registry entries are created
    device_entry = device_reg.async_get_device({("mqtt", "0AFFD2")})
    assert device_entry is not None
    entity_entry = entity_reg.async_get("sensor.mqtt_sensor")
    assert entity_entry is not None

    state = hass.states.get("sensor.mqtt_sensor")
    assert state is not None

    # Remove MQTT from the device
    await ws_client.send_json(
        {
            "id": 6,
            "type": "mqtt/device/remove",
            "device_id": device_entry.id,
        }
    )
    response = await ws_client.receive_json()
    assert response["success"]
    await hass.async_block_till_done()
    await hass.async_block_till_done()

    # Verify device and registry entries are cleared
    device_entry = device_reg.async_get_device({("mqtt", "0AFFD2")})
    assert device_entry is None
    entity_entry = entity_reg.async_get("sensor.mqtt_sensor")
    assert entity_entry is None

    # Verify state is removed
    state = hass.states.get("sensor.mqtt_sensor")
    assert state is None
    await hass.async_block_till_done()

    # Verify retained discovery topic has been cleared
    mqtt_mock.async_publish.assert_called_once_with(
        "homeassistant/sensor/bla/config", "", 0, True
    )


async def test_cleanup_device_mqtt(hass, device_reg, entity_reg, mqtt_mock):
    """Test discvered device is cleaned up when removed through MQTT."""
    data = (
        '{ "device":{"identifiers":["0AFFD2"]},'
        '  "state_topic": "foobar/sensor",'
        '  "unique_id": "unique" }'
    )

    async_fire_mqtt_message(hass, "homeassistant/sensor/bla/config", data)
    await hass.async_block_till_done()

    # Verify device and registry entries are created
    device_entry = device_reg.async_get_device({("mqtt", "0AFFD2")})
    assert device_entry is not None
    entity_entry = entity_reg.async_get("sensor.mqtt_sensor")
    assert entity_entry is not None

    state = hass.states.get("sensor.mqtt_sensor")
    assert state is not None

    async_fire_mqtt_message(hass, "homeassistant/sensor/bla/config", "")
    await hass.async_block_till_done()
    await hass.async_block_till_done()

    # Verify device and registry entries are cleared
    device_entry = device_reg.async_get_device({("mqtt", "0AFFD2")})
    assert device_entry is None
    entity_entry = entity_reg.async_get("sensor.mqtt_sensor")
    assert entity_entry is None

    # Verify state is removed
    state = hass.states.get("sensor.mqtt_sensor")
    assert state is None
    await hass.async_block_till_done()

    # Verify retained discovery topics have not been cleared again
    mqtt_mock.async_publish.assert_not_called()


async def test_cleanup_device_multiple_config_entries(
    hass, hass_ws_client, device_reg, entity_reg, mqtt_mock
):
    """Test discovered device is cleaned up when entry removed from device."""
    assert await async_setup_component(hass, "config", {})
    ws_client = await hass_ws_client(hass)

    config_entry = MockConfigEntry(domain="test", data={})
    config_entry.add_to_hass(hass)
    device_entry = device_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={("mac", "12:34:56:AB:CD:EF")},
    )

    mqtt_config_entry = hass.config_entries.async_entries(mqtt.DOMAIN)[0]

    sensor_config = {
        "device": {"connections": [["mac", "12:34:56:AB:CD:EF"]]},
        "state_topic": "foobar/sensor",
        "unique_id": "unique",
    }
    tag_config = {
        "device": {"connections": [["mac", "12:34:56:AB:CD:EF"]]},
        "topic": "test-topic",
    }
    trigger_config = {
        "automation_type": "trigger",
        "topic": "test-topic",
        "type": "foo",
        "subtype": "bar",
        "device": {"connections": [["mac", "12:34:56:AB:CD:EF"]]},
    }

    sensor_data = json.dumps(sensor_config)
    tag_data = json.dumps(tag_config)
    trigger_data = json.dumps(trigger_config)
    async_fire_mqtt_message(hass, "homeassistant/sensor/bla/config", sensor_data)
    async_fire_mqtt_message(hass, "homeassistant/tag/bla/config", tag_data)
    async_fire_mqtt_message(
        hass, "homeassistant/device_automation/bla/config", trigger_data
    )
    await hass.async_block_till_done()

    # Verify device and registry entries are created
    device_entry = device_reg.async_get_device(set(), {("mac", "12:34:56:AB:CD:EF")})
    assert device_entry is not None
    assert device_entry.config_entries == {
        mqtt_config_entry.entry_id,
        config_entry.entry_id,
    }
    entity_entry = entity_reg.async_get("sensor.mqtt_sensor")
    assert entity_entry is not None

    state = hass.states.get("sensor.mqtt_sensor")
    assert state is not None

    # Remove MQTT from the device
    await ws_client.send_json(
        {
            "id": 6,
            "type": "mqtt/device/remove",
            "device_id": device_entry.id,
        }
    )
    response = await ws_client.receive_json()
    assert response["success"]

    await hass.async_block_till_done()
    await hass.async_block_till_done()

    # Verify device is still there but entity is cleared
    device_entry = device_reg.async_get_device(set(), {("mac", "12:34:56:AB:CD:EF")})
    assert device_entry is not None
    entity_entry = entity_reg.async_get("sensor.mqtt_sensor")
    assert device_entry.config_entries == {config_entry.entry_id}
    assert entity_entry is None

    # Verify state is removed
    state = hass.states.get("sensor.mqtt_sensor")
    assert state is None
    await hass.async_block_till_done()

    # Verify retained discovery topic has been cleared
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("homeassistant/sensor/bla/config", "", 0, True),
            call("homeassistant/tag/bla/config", "", 0, True),
            call("homeassistant/device_automation/bla/config", "", 0, True),
        ],
        any_order=True,
    )


async def test_cleanup_device_multiple_config_entries_mqtt(
    hass, device_reg, entity_reg, mqtt_mock
):
    """Test discovered device is cleaned up when removed through MQTT."""
    config_entry = MockConfigEntry(domain="test", data={})
    config_entry.add_to_hass(hass)
    device_entry = device_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={("mac", "12:34:56:AB:CD:EF")},
    )

    mqtt_config_entry = hass.config_entries.async_entries(mqtt.DOMAIN)[0]

    sensor_config = {
        "device": {"connections": [["mac", "12:34:56:AB:CD:EF"]]},
        "state_topic": "foobar/sensor",
        "unique_id": "unique",
    }
    tag_config = {
        "device": {"connections": [["mac", "12:34:56:AB:CD:EF"]]},
        "topic": "test-topic",
    }
    trigger_config = {
        "automation_type": "trigger",
        "topic": "test-topic",
        "type": "foo",
        "subtype": "bar",
        "device": {"connections": [["mac", "12:34:56:AB:CD:EF"]]},
    }

    sensor_data = json.dumps(sensor_config)
    tag_data = json.dumps(tag_config)
    trigger_data = json.dumps(trigger_config)
    async_fire_mqtt_message(hass, "homeassistant/sensor/bla/config", sensor_data)
    async_fire_mqtt_message(hass, "homeassistant/tag/bla/config", tag_data)
    async_fire_mqtt_message(
        hass, "homeassistant/device_automation/bla/config", trigger_data
    )
    await hass.async_block_till_done()

    # Verify device and registry entries are created
    device_entry = device_reg.async_get_device(set(), {("mac", "12:34:56:AB:CD:EF")})
    assert device_entry is not None
    assert device_entry.config_entries == {
        mqtt_config_entry.entry_id,
        config_entry.entry_id,
    }
    entity_entry = entity_reg.async_get("sensor.mqtt_sensor")
    assert entity_entry is not None

    state = hass.states.get("sensor.mqtt_sensor")
    assert state is not None

    # Send MQTT messages to remove
    async_fire_mqtt_message(hass, "homeassistant/sensor/bla/config", "")
    async_fire_mqtt_message(hass, "homeassistant/tag/bla/config", "")
    async_fire_mqtt_message(hass, "homeassistant/device_automation/bla/config", "")

    await hass.async_block_till_done()
    await hass.async_block_till_done()

    # Verify device is still there but entity is cleared
    device_entry = device_reg.async_get_device(set(), {("mac", "12:34:56:AB:CD:EF")})
    assert device_entry is not None
    entity_entry = entity_reg.async_get("sensor.mqtt_sensor")
    assert device_entry.config_entries == {config_entry.entry_id}
    assert entity_entry is None

    # Verify state is removed
    state = hass.states.get("sensor.mqtt_sensor")
    assert state is None
    await hass.async_block_till_done()

    # Verify retained discovery topics have not been cleared again
    mqtt_mock.async_publish.assert_not_called()


async def test_discovery_expansion(hass, mqtt_mock, caplog):
    """Test expansion of abbreviated discovery payload."""
    data = (
        '{ "~": "some/base/topic",'
        '  "name": "DiscoveryExpansionTest1",'
        '  "stat_t": "test_topic/~",'
        '  "cmd_t": "~/test_topic",'
        '  "availability": ['
        "    {"
        '      "topic":"~/avail_item1",'
        '      "payload_available": "available",'
        '      "payload_not_available": "not_available"'
        "    },"
        "    {"
        '      "topic":"avail_item2/~",'
        '      "payload_available": "available",'
        '      "payload_not_available": "not_available"'
        "    }"
        "  ],"
        '  "dev":{'
        '    "ids":["5706DF"],'
        '    "name":"DiscoveryExpansionTest1 Device",'
        '    "mdl":"Generic",'
        '    "sw":"1.2.3.4",'
        '    "mf":"None",'
        '    "sa":"default_area"'
        "  }"
        "}"
    )

    async_fire_mqtt_message(hass, "homeassistant/switch/bla/config", data)
    await hass.async_block_till_done()

    state = hass.states.get("switch.DiscoveryExpansionTest1")
    assert state.state == STATE_UNAVAILABLE

    async_fire_mqtt_message(hass, "avail_item2/some/base/topic", "available")
    await hass.async_block_till_done()

    state = hass.states.get("switch.DiscoveryExpansionTest1")
    assert state is not None
    assert state.name == "DiscoveryExpansionTest1"
    assert ("switch", "bla") in hass.data[ALREADY_DISCOVERED]
    assert state.state == STATE_UNKNOWN

    async_fire_mqtt_message(hass, "test_topic/some/base/topic", "ON")

    state = hass.states.get("switch.DiscoveryExpansionTest1")
    assert state.state == STATE_ON

    async_fire_mqtt_message(hass, "some/base/topic/avail_item1", "not_available")
    await hass.async_block_till_done()

    state = hass.states.get("switch.DiscoveryExpansionTest1")
    assert state.state == STATE_UNAVAILABLE


async def test_discovery_expansion_2(hass, mqtt_mock, caplog):
    """Test expansion of abbreviated discovery payload."""
    data = (
        '{ "~": "some/base/topic",'
        '  "name": "DiscoveryExpansionTest1",'
        '  "stat_t": "test_topic/~",'
        '  "cmd_t": "~/test_topic",'
        '  "availability": {'
        '    "topic":"~/avail_item1",'
        '    "payload_available": "available",'
        '    "payload_not_available": "not_available"'
        "  },"
        '  "dev":{'
        '    "ids":["5706DF"],'
        '    "name":"DiscoveryExpansionTest1 Device",'
        '    "mdl":"Generic",'
        '    "sw":"1.2.3.4",'
        '    "mf":"None",'
        '    "sa":"default_area"'
        "  }"
        "}"
    )

    async_fire_mqtt_message(hass, "homeassistant/switch/bla/config", data)
    await hass.async_block_till_done()

    state = hass.states.get("switch.DiscoveryExpansionTest1")
    assert state.state == STATE_UNAVAILABLE

    async_fire_mqtt_message(hass, "some/base/topic/avail_item1", "available")
    await hass.async_block_till_done()

    state = hass.states.get("switch.DiscoveryExpansionTest1")
    assert state is not None
    assert state.name == "DiscoveryExpansionTest1"
    assert ("switch", "bla") in hass.data[ALREADY_DISCOVERED]
    assert state.state == STATE_UNKNOWN


@pytest.mark.no_fail_on_log_exception
async def test_discovery_expansion_3(hass, mqtt_mock, caplog):
    """Test expansion of broken discovery payload."""
    data = (
        '{ "~": "some/base/topic",'
        '  "name": "DiscoveryExpansionTest1",'
        '  "stat_t": "test_topic/~",'
        '  "cmd_t": "~/test_topic",'
        '  "availability": "incorrect",'
        '  "dev":{'
        '    "ids":["5706DF"],'
        '    "name":"DiscoveryExpansionTest1 Device",'
        '    "mdl":"Generic",'
        '    "sw":"1.2.3.4",'
        '    "mf":"None",'
        '    "sa":"default_area"'
        "  }"
        "}"
    )

    async_fire_mqtt_message(hass, "homeassistant/switch/bla/config", data)
    await hass.async_block_till_done()
    assert hass.states.get("switch.DiscoveryExpansionTest1") is None
    # Make sure the malformed availability data does not trip up discovery by asserting
    # there are schema valdiation errors in the log
    assert (
        "voluptuous.error.MultipleInvalid: expected a dictionary @ data['availability'][0]"
        in caplog.text
    )


async def test_discovery_expansion_without_encoding_and_value_template_1(
    hass, mqtt_mock, caplog
):
    """Test expansion of raw availability payload with a template as list."""
    data = (
        '{ "~": "some/base/topic",'
        '  "name": "DiscoveryExpansionTest1",'
        '  "stat_t": "test_topic/~",'
        '  "cmd_t": "~/test_topic",'
        '  "encoding":"",'
        '  "availability": [{'
        '    "topic":"~/avail_item1",'
        '    "payload_available": "1",'
        '    "payload_not_available": "0",'
        '    "value_template":"{{value|unpack(\'b\')}}"'
        "  }],"
        '  "dev":{'
        '    "ids":["5706DF"],'
        '    "name":"DiscoveryExpansionTest1 Device",'
        '    "mdl":"Generic",'
        '    "sw":"1.2.3.4",'
        '    "mf":"None",'
        '    "sa":"default_area"'
        "  }"
        "}"
    )

    async_fire_mqtt_message(hass, "homeassistant/switch/bla/config", data)
    await hass.async_block_till_done()

    state = hass.states.get("switch.DiscoveryExpansionTest1")
    assert state.state == STATE_UNAVAILABLE

    async_fire_mqtt_message(hass, "some/base/topic/avail_item1", b"\x01")
    await hass.async_block_till_done()

    state = hass.states.get("switch.DiscoveryExpansionTest1")
    assert state is not None
    assert state.name == "DiscoveryExpansionTest1"
    assert ("switch", "bla") in hass.data[ALREADY_DISCOVERED]
    assert state.state == STATE_UNKNOWN

    async_fire_mqtt_message(hass, "some/base/topic/avail_item1", b"\x00")

    state = hass.states.get("switch.DiscoveryExpansionTest1")
    assert state.state == STATE_UNAVAILABLE


async def test_discovery_expansion_without_encoding_and_value_template_2(
    hass, mqtt_mock, caplog
):
    """Test expansion of raw availability payload with a template directly."""
    data = (
        '{ "~": "some/base/topic",'
        '  "name": "DiscoveryExpansionTest1",'
        '  "stat_t": "test_topic/~",'
        '  "cmd_t": "~/test_topic",'
        '  "availability_topic":"~/avail_item1",'
        '  "payload_available": "1",'
        '  "payload_not_available": "0",'
        '  "encoding":"",'
        '  "availability_template":"{{ value | unpack(\'b\') }}",'
        '  "dev":{'
        '    "ids":["5706DF"],'
        '    "name":"DiscoveryExpansionTest1 Device",'
        '    "mdl":"Generic",'
        '    "sw":"1.2.3.4",'
        '    "mf":"None",'
        '    "sa":"default_area"'
        "  }"
        "}"
    )

    async_fire_mqtt_message(hass, "homeassistant/switch/bla/config", data)
    await hass.async_block_till_done()

    state = hass.states.get("switch.DiscoveryExpansionTest1")
    assert state.state == STATE_UNAVAILABLE

    async_fire_mqtt_message(hass, "some/base/topic/avail_item1", b"\x01")
    await hass.async_block_till_done()

    state = hass.states.get("switch.DiscoveryExpansionTest1")
    assert state is not None
    assert state.name == "DiscoveryExpansionTest1"
    assert ("switch", "bla") in hass.data[ALREADY_DISCOVERED]
    assert state.state == STATE_UNKNOWN

    async_fire_mqtt_message(hass, "some/base/topic/avail_item1", b"\x00")

    state = hass.states.get("switch.DiscoveryExpansionTest1")
    assert state.state == STATE_UNAVAILABLE


ABBREVIATIONS_WHITE_LIST = [
    # MQTT client/server/trigger settings
    "CONF_BIRTH_MESSAGE",
    "CONF_BROKER",
    "CONF_CERTIFICATE",
    "CONF_CLIENT_CERT",
    "CONF_CLIENT_ID",
    "CONF_CLIENT_KEY",
    "CONF_DISCOVERY",
    "CONF_DISCOVERY_ID",
    "CONF_DISCOVERY_PREFIX",
    "CONF_EMBEDDED",
    "CONF_KEEPALIVE",
    "CONF_TLS_INSECURE",
    "CONF_TLS_VERSION",
    "CONF_WILL_MESSAGE",
    # Undocumented device configuration
    "CONF_DEPRECATED_VIA_HUB",
    "CONF_VIA_DEVICE",
    # Already short
    "CONF_FAN_MODE_LIST",
    "CONF_HOLD_LIST",
    "CONF_HS",
    "CONF_MODE_LIST",
    "CONF_PRECISION",
    "CONF_QOS",
    "CONF_SCHEMA",
    "CONF_SWING_MODE_LIST",
    "CONF_TEMP_STEP",
]


async def test_missing_discover_abbreviations(hass, mqtt_mock, caplog):
    """Check MQTT platforms for missing abbreviations."""
    missing = []
    regex = re.compile(r"(CONF_[a-zA-Z\d_]*) *= *[\'\"]([a-zA-Z\d_]*)[\'\"]")
    for fil in Path(mqtt.__file__).parent.rglob("*.py"):
        if fil.name == "trigger.py":
            continue
        with open(fil) as file:
            matches = re.findall(regex, file.read())
            for match in matches:
                if (
                    match[1] not in ABBREVIATIONS.values()
                    and match[1] not in DEVICE_ABBREVIATIONS.values()
                    and match[0] not in ABBREVIATIONS_WHITE_LIST
                ):
                    missing.append(
                        "{}: no abbreviation for {} ({})".format(
                            fil, match[1], match[0]
                        )
                    )

    assert not missing


async def test_no_implicit_state_topic_switch(hass, mqtt_mock, caplog):
    """Test no implicit state topic for switch."""
    data = '{ "name": "Test1",' '  "command_topic": "cmnd"' "}"

    async_fire_mqtt_message(hass, "homeassistant/switch/bla/config", data)
    await hass.async_block_till_done()
    assert "implicit state_topic is deprecated" not in caplog.text

    state = hass.states.get("switch.Test1")
    assert state is not None
    assert state.name == "Test1"
    assert ("switch", "bla") in hass.data[ALREADY_DISCOVERED]
    assert state.state == STATE_UNKNOWN
    assert state.attributes["assumed_state"] is True

    async_fire_mqtt_message(hass, "homeassistant/switch/bla/state", "ON")

    state = hass.states.get("switch.Test1")
    assert state.state == STATE_UNKNOWN


@pytest.mark.parametrize(
    "mqtt_config",
    [
        {
            mqtt.CONF_BROKER: "mock-broker",
            mqtt.CONF_DISCOVERY_PREFIX: "my_home/homeassistant/register",
        }
    ],
)
async def test_complex_discovery_topic_prefix(hass, mqtt_mock, caplog):
    """Tests handling of discovery topic prefix with multiple slashes."""
    async_fire_mqtt_message(
        hass,
        ("my_home/homeassistant/register/binary_sensor/node1/object1/config"),
        '{ "name": "Beer", "state_topic": "test-topic" }',
    )
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.beer")

    assert state is not None
    assert state.name == "Beer"
    assert ("binary_sensor", "node1 object1") in hass.data[ALREADY_DISCOVERED]


async def test_mqtt_integration_discovery_subscribe_unsubscribe(
    hass, mqtt_client_mock, mqtt_mock
):
    """Check MQTT integration discovery subscribe and unsubscribe."""
    mock_entity_platform(hass, "config_flow.comp", None)

    entry = hass.config_entries.async_entries("mqtt")[0]
    mqtt_mock().connected = True

    with patch(
        "homeassistant.components.mqtt.discovery.async_get_mqtt",
        return_value={"comp": ["comp/discovery/#"]},
    ):
        await async_start(hass, "homeassistant", entry)
        await hass.async_block_till_done()

    mqtt_client_mock.subscribe.assert_any_call("comp/discovery/#", 0)
    assert not mqtt_client_mock.unsubscribe.called

    class TestFlow(config_entries.ConfigFlow):
        """Test flow."""

        async def async_step_mqtt(self, discovery_info):
            """Test mqtt step."""
            return self.async_abort(reason="already_configured")

    with patch.dict(config_entries.HANDLERS, {"comp": TestFlow}):
        mqtt_client_mock.subscribe.assert_any_call("comp/discovery/#", 0)
        assert not mqtt_client_mock.unsubscribe.called

        async_fire_mqtt_message(hass, "comp/discovery/bla/config", "")
        await hass.async_block_till_done()
        mqtt_client_mock.unsubscribe.assert_called_once_with("comp/discovery/#")
        mqtt_client_mock.unsubscribe.reset_mock()

        async_fire_mqtt_message(hass, "comp/discovery/bla/config", "")
        await hass.async_block_till_done()
        assert not mqtt_client_mock.unsubscribe.called


async def test_mqtt_discovery_unsubscribe_once(hass, mqtt_client_mock, mqtt_mock):
    """Check MQTT integration discovery unsubscribe once."""
    mock_entity_platform(hass, "config_flow.comp", None)

    entry = hass.config_entries.async_entries("mqtt")[0]
    mqtt_mock().connected = True

    with patch(
        "homeassistant.components.mqtt.discovery.async_get_mqtt",
        return_value={"comp": ["comp/discovery/#"]},
    ):
        await async_start(hass, "homeassistant", entry)
        await hass.async_block_till_done()

    mqtt_client_mock.subscribe.assert_any_call("comp/discovery/#", 0)
    assert not mqtt_client_mock.unsubscribe.called

    class TestFlow(config_entries.ConfigFlow):
        """Test flow."""

        async def async_step_mqtt(self, discovery_info):
            """Test mqtt step."""
            return self.async_abort(reason="already_configured")

    with patch.dict(config_entries.HANDLERS, {"comp": TestFlow}):
        async_fire_mqtt_message(hass, "comp/discovery/bla/config", "")
        async_fire_mqtt_message(hass, "comp/discovery/bla/config", "")
        await hass.async_block_till_done()
        await hass.async_block_till_done()
        mqtt_client_mock.unsubscribe.assert_called_once_with("comp/discovery/#")
