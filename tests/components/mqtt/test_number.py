"""The tests for mqtt number component."""
import json
from unittest.mock import patch

import pytest

from homeassistant.components import number
from homeassistant.components.mqtt.number import (
    CONF_MAX,
    CONF_MIN,
    MQTT_NUMBER_ATTRIBUTES_BLOCKED,
)
from homeassistant.components.number import (
    ATTR_MAX,
    ATTR_MIN,
    ATTR_STEP,
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import (
    ATTR_ASSUMED_STATE,
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
)
import homeassistant.core as ha
from homeassistant.setup import async_setup_component

from .test_common import (
    help_test_availability_when_connection_lost,
    help_test_availability_without_topic,
    help_test_custom_availability_payload,
    help_test_default_availability_payload,
    help_test_discovery_broken,
    help_test_discovery_removal,
    help_test_discovery_update,
    help_test_discovery_update_attr,
    help_test_discovery_update_unchanged,
    help_test_encoding_subscribable_topics,
    help_test_entity_debug_info_message,
    help_test_entity_device_info_remove,
    help_test_entity_device_info_update,
    help_test_entity_device_info_with_connection,
    help_test_entity_device_info_with_identifier,
    help_test_entity_id_update_discovery_update,
    help_test_entity_id_update_subscriptions,
    help_test_publishing_with_custom_encoding,
    help_test_reloadable,
    help_test_reloadable_late,
    help_test_setting_attribute_via_mqtt_json_message,
    help_test_setting_attribute_with_template,
    help_test_setting_blocked_attribute_via_mqtt_json_message,
    help_test_unique_id,
    help_test_update_with_json_attrs_bad_JSON,
    help_test_update_with_json_attrs_not_dict,
)

from tests.common import async_fire_mqtt_message

DEFAULT_CONFIG = {
    number.DOMAIN: {"platform": "mqtt", "name": "test", "command_topic": "test-topic"}
}


async def test_run_number_setup(hass, mqtt_mock):
    """Test that it fetches the given payload."""
    topic = "test/number"
    await async_setup_component(
        hass,
        "number",
        {
            "number": {
                "platform": "mqtt",
                "state_topic": topic,
                "command_topic": topic,
                "name": "Test Number",
                "unit_of_measurement": "my unit",
                "payload_reset": "reset!",
            }
        },
    )
    await hass.async_block_till_done()

    async_fire_mqtt_message(hass, topic, "10")

    await hass.async_block_till_done()

    state = hass.states.get("number.test_number")
    assert state.state == "10"
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == "my unit"

    async_fire_mqtt_message(hass, topic, "20.5")

    await hass.async_block_till_done()

    state = hass.states.get("number.test_number")
    assert state.state == "20.5"
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == "my unit"

    async_fire_mqtt_message(hass, topic, "reset!")

    await hass.async_block_till_done()

    state = hass.states.get("number.test_number")
    assert state.state == "unknown"
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == "my unit"


async def test_value_template(hass, mqtt_mock):
    """Test that it fetches the given payload with a template."""
    topic = "test/number"
    await async_setup_component(
        hass,
        "number",
        {
            "number": {
                "platform": "mqtt",
                "state_topic": topic,
                "command_topic": topic,
                "name": "Test Number",
                "value_template": "{{ value_json.val }}",
            }
        },
    )
    await hass.async_block_till_done()

    async_fire_mqtt_message(hass, topic, '{"val":10}')

    await hass.async_block_till_done()

    state = hass.states.get("number.test_number")
    assert state.state == "10"

    async_fire_mqtt_message(hass, topic, '{"val":20.5}')

    await hass.async_block_till_done()

    state = hass.states.get("number.test_number")
    assert state.state == "20.5"

    async_fire_mqtt_message(hass, topic, '{"val":null}')

    await hass.async_block_till_done()

    state = hass.states.get("number.test_number")
    assert state.state == "unknown"


async def test_run_number_service_optimistic(hass, mqtt_mock):
    """Test that set_value service works in optimistic mode."""
    topic = "test/number"

    fake_state = ha.State("switch.test", "3")

    with patch(
        "homeassistant.helpers.restore_state.RestoreEntity.async_get_last_state",
        return_value=fake_state,
    ):
        assert await async_setup_component(
            hass,
            number.DOMAIN,
            {
                "number": {
                    "platform": "mqtt",
                    "command_topic": topic,
                    "name": "Test Number",
                }
            },
        )
        await hass.async_block_till_done()

    state = hass.states.get("number.test_number")
    assert state.state == "3"
    assert state.attributes.get(ATTR_ASSUMED_STATE)

    # Integer
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.test_number", ATTR_VALUE: 30},
        blocking=True,
    )

    mqtt_mock.async_publish.assert_called_once_with(topic, "30", 0, False)
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("number.test_number")
    assert state.state == "30"

    # Float with no decimal -> integer
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.test_number", ATTR_VALUE: 42.0},
        blocking=True,
    )

    mqtt_mock.async_publish.assert_called_once_with(topic, "42", 0, False)
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("number.test_number")
    assert state.state == "42"

    # Float with decimal -> float
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.test_number", ATTR_VALUE: 42.1},
        blocking=True,
    )

    mqtt_mock.async_publish.assert_called_once_with(topic, "42.1", 0, False)
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("number.test_number")
    assert state.state == "42.1"


async def test_run_number_service_optimistic_with_command_template(hass, mqtt_mock):
    """Test that set_value service works in optimistic mode and with a command_template."""
    topic = "test/number"

    fake_state = ha.State("switch.test", "3")

    with patch(
        "homeassistant.helpers.restore_state.RestoreEntity.async_get_last_state",
        return_value=fake_state,
    ):
        assert await async_setup_component(
            hass,
            number.DOMAIN,
            {
                "number": {
                    "platform": "mqtt",
                    "command_topic": topic,
                    "name": "Test Number",
                    "command_template": '{"number": {{ value }} }',
                }
            },
        )
        await hass.async_block_till_done()

    state = hass.states.get("number.test_number")
    assert state.state == "3"
    assert state.attributes.get(ATTR_ASSUMED_STATE)

    # Integer
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.test_number", ATTR_VALUE: 30},
        blocking=True,
    )

    mqtt_mock.async_publish.assert_called_once_with(topic, '{"number": 30 }', 0, False)
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("number.test_number")
    assert state.state == "30"

    # Float with no decimal -> integer
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.test_number", ATTR_VALUE: 42.0},
        blocking=True,
    )

    mqtt_mock.async_publish.assert_called_once_with(topic, '{"number": 42 }', 0, False)
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("number.test_number")
    assert state.state == "42"

    # Float with decimal -> float
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.test_number", ATTR_VALUE: 42.1},
        blocking=True,
    )

    mqtt_mock.async_publish.assert_called_once_with(
        topic, '{"number": 42.1 }', 0, False
    )
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("number.test_number")
    assert state.state == "42.1"


async def test_run_number_service(hass, mqtt_mock):
    """Test that set_value service works in non optimistic mode."""
    cmd_topic = "test/number/set"
    state_topic = "test/number"

    assert await async_setup_component(
        hass,
        number.DOMAIN,
        {
            "number": {
                "platform": "mqtt",
                "command_topic": cmd_topic,
                "state_topic": state_topic,
                "name": "Test Number",
            }
        },
    )
    await hass.async_block_till_done()

    async_fire_mqtt_message(hass, state_topic, "32")
    state = hass.states.get("number.test_number")
    assert state.state == "32"

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.test_number", ATTR_VALUE: 30},
        blocking=True,
    )
    mqtt_mock.async_publish.assert_called_once_with(cmd_topic, "30", 0, False)
    state = hass.states.get("number.test_number")
    assert state.state == "32"


async def test_run_number_service_with_command_template(hass, mqtt_mock):
    """Test that set_value service works in non optimistic mode and with a command_template."""
    cmd_topic = "test/number/set"
    state_topic = "test/number"

    assert await async_setup_component(
        hass,
        number.DOMAIN,
        {
            "number": {
                "platform": "mqtt",
                "command_topic": cmd_topic,
                "state_topic": state_topic,
                "name": "Test Number",
                "command_template": '{"number": {{ value }} }',
            }
        },
    )
    await hass.async_block_till_done()

    async_fire_mqtt_message(hass, state_topic, "32")
    state = hass.states.get("number.test_number")
    assert state.state == "32"

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.test_number", ATTR_VALUE: 30},
        blocking=True,
    )
    mqtt_mock.async_publish.assert_called_once_with(
        cmd_topic, '{"number": 30 }', 0, False
    )
    state = hass.states.get("number.test_number")
    assert state.state == "32"


async def test_availability_when_connection_lost(hass, mqtt_mock):
    """Test availability after MQTT disconnection."""
    await help_test_availability_when_connection_lost(
        hass, mqtt_mock, number.DOMAIN, DEFAULT_CONFIG
    )


async def test_availability_without_topic(hass, mqtt_mock):
    """Test availability without defined availability topic."""
    await help_test_availability_without_topic(
        hass, mqtt_mock, number.DOMAIN, DEFAULT_CONFIG
    )


async def test_default_availability_payload(hass, mqtt_mock):
    """Test availability by default payload with defined topic."""
    await help_test_default_availability_payload(
        hass, mqtt_mock, number.DOMAIN, DEFAULT_CONFIG
    )


async def test_custom_availability_payload(hass, mqtt_mock):
    """Test availability by custom payload with defined topic."""
    await help_test_custom_availability_payload(
        hass, mqtt_mock, number.DOMAIN, DEFAULT_CONFIG
    )


async def test_setting_attribute_via_mqtt_json_message(hass, mqtt_mock):
    """Test the setting of attribute via MQTT with JSON payload."""
    await help_test_setting_attribute_via_mqtt_json_message(
        hass, mqtt_mock, number.DOMAIN, DEFAULT_CONFIG
    )


async def test_setting_blocked_attribute_via_mqtt_json_message(hass, mqtt_mock):
    """Test the setting of attribute via MQTT with JSON payload."""
    await help_test_setting_blocked_attribute_via_mqtt_json_message(
        hass, mqtt_mock, number.DOMAIN, DEFAULT_CONFIG, MQTT_NUMBER_ATTRIBUTES_BLOCKED
    )


async def test_setting_attribute_with_template(hass, mqtt_mock):
    """Test the setting of attribute via MQTT with JSON payload."""
    await help_test_setting_attribute_with_template(
        hass, mqtt_mock, number.DOMAIN, DEFAULT_CONFIG
    )


async def test_update_with_json_attrs_not_dict(hass, mqtt_mock, caplog):
    """Test attributes get extracted from a JSON result."""
    await help_test_update_with_json_attrs_not_dict(
        hass, mqtt_mock, caplog, number.DOMAIN, DEFAULT_CONFIG
    )


async def test_update_with_json_attrs_bad_JSON(hass, mqtt_mock, caplog):
    """Test attributes get extracted from a JSON result."""
    await help_test_update_with_json_attrs_bad_JSON(
        hass, mqtt_mock, caplog, number.DOMAIN, DEFAULT_CONFIG
    )


async def test_discovery_update_attr(hass, mqtt_mock, caplog):
    """Test update of discovered MQTTAttributes."""
    await help_test_discovery_update_attr(
        hass, mqtt_mock, caplog, number.DOMAIN, DEFAULT_CONFIG
    )


async def test_unique_id(hass, mqtt_mock):
    """Test unique id option only creates one number per unique_id."""
    config = {
        number.DOMAIN: [
            {
                "platform": "mqtt",
                "name": "Test 1",
                "state_topic": "test-topic",
                "command_topic": "test-topic",
                "unique_id": "TOTALLY_UNIQUE",
            },
            {
                "platform": "mqtt",
                "name": "Test 2",
                "state_topic": "test-topic",
                "command_topic": "test-topic",
                "unique_id": "TOTALLY_UNIQUE",
            },
        ]
    }
    await help_test_unique_id(hass, mqtt_mock, number.DOMAIN, config)


async def test_discovery_removal_number(hass, mqtt_mock, caplog):
    """Test removal of discovered number."""
    data = json.dumps(DEFAULT_CONFIG[number.DOMAIN])
    await help_test_discovery_removal(hass, mqtt_mock, caplog, number.DOMAIN, data)


async def test_discovery_update_number(hass, mqtt_mock, caplog):
    """Test update of discovered number."""
    config1 = {
        "name": "Beer",
        "state_topic": "test-topic",
        "command_topic": "test-topic",
    }
    config2 = {
        "name": "Milk",
        "state_topic": "test-topic",
        "command_topic": "test-topic",
    }

    await help_test_discovery_update(
        hass, mqtt_mock, caplog, number.DOMAIN, config1, config2
    )


async def test_discovery_update_unchanged_number(hass, mqtt_mock, caplog):
    """Test update of discovered number."""
    data1 = (
        '{ "name": "Beer", "state_topic": "test-topic", "command_topic": "test-topic"}'
    )
    with patch(
        "homeassistant.components.mqtt.number.MqttNumber.discovery_update"
    ) as discovery_update:
        await help_test_discovery_update_unchanged(
            hass, mqtt_mock, caplog, number.DOMAIN, data1, discovery_update
        )


@pytest.mark.no_fail_on_log_exception
async def test_discovery_broken(hass, mqtt_mock, caplog):
    """Test handling of bad discovery message."""
    data1 = '{ "name": "Beer" }'
    data2 = (
        '{ "name": "Milk", "state_topic": "test-topic", "command_topic": "test-topic"}'
    )

    await help_test_discovery_broken(
        hass, mqtt_mock, caplog, number.DOMAIN, data1, data2
    )


async def test_entity_device_info_with_connection(hass, mqtt_mock):
    """Test MQTT number device registry integration."""
    await help_test_entity_device_info_with_connection(
        hass, mqtt_mock, number.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_device_info_with_identifier(hass, mqtt_mock):
    """Test MQTT number device registry integration."""
    await help_test_entity_device_info_with_identifier(
        hass, mqtt_mock, number.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_device_info_update(hass, mqtt_mock):
    """Test device registry update."""
    await help_test_entity_device_info_update(
        hass, mqtt_mock, number.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_device_info_remove(hass, mqtt_mock):
    """Test device registry remove."""
    await help_test_entity_device_info_remove(
        hass, mqtt_mock, number.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_id_update_subscriptions(hass, mqtt_mock):
    """Test MQTT subscriptions are managed when entity_id is updated."""
    await help_test_entity_id_update_subscriptions(
        hass, mqtt_mock, number.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_id_update_discovery_update(hass, mqtt_mock):
    """Test MQTT discovery update when entity_id is updated."""
    await help_test_entity_id_update_discovery_update(
        hass, mqtt_mock, number.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_debug_info_message(hass, mqtt_mock):
    """Test MQTT debug info."""
    await help_test_entity_debug_info_message(
        hass,
        mqtt_mock,
        number.DOMAIN,
        DEFAULT_CONFIG,
        SERVICE_SET_VALUE,
        service_parameters={ATTR_VALUE: 45},
        command_payload="45",
        state_payload="1",
    )


async def test_min_max_step_attributes(hass, mqtt_mock):
    """Test min/max/step attributes."""
    topic = "test/number"
    await async_setup_component(
        hass,
        "number",
        {
            "number": {
                "platform": "mqtt",
                "state_topic": topic,
                "command_topic": topic,
                "name": "Test Number",
                "min": 5,
                "max": 110,
                "step": 20,
            }
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("number.test_number")
    assert state.attributes.get(ATTR_MIN) == 5
    assert state.attributes.get(ATTR_MAX) == 110
    assert state.attributes.get(ATTR_STEP) == 20


async def test_invalid_min_max_attributes(hass, caplog, mqtt_mock):
    """Test invalid min/max attributes."""
    topic = "test/number"
    await async_setup_component(
        hass,
        "number",
        {
            "number": {
                "platform": "mqtt",
                "state_topic": topic,
                "command_topic": topic,
                "name": "Test Number",
                "min": 35,
                "max": 10,
            }
        },
    )
    await hass.async_block_till_done()

    assert f"'{CONF_MAX}' must be > '{CONF_MIN}'" in caplog.text


async def test_mqtt_payload_not_a_number_warning(hass, caplog, mqtt_mock):
    """Test warning for MQTT payload which is not a number."""
    topic = "test/number"
    await async_setup_component(
        hass,
        "number",
        {
            "number": {
                "platform": "mqtt",
                "state_topic": topic,
                "command_topic": topic,
                "name": "Test Number",
            }
        },
    )
    await hass.async_block_till_done()

    async_fire_mqtt_message(hass, topic, "not_a_number")

    await hass.async_block_till_done()

    assert "Payload 'not_a_number' is not a Number" in caplog.text


async def test_mqtt_payload_out_of_range_error(hass, caplog, mqtt_mock):
    """Test error when MQTT payload is out of min/max range."""
    topic = "test/number"
    await async_setup_component(
        hass,
        "number",
        {
            "number": {
                "platform": "mqtt",
                "state_topic": topic,
                "command_topic": topic,
                "name": "Test Number",
                "min": 5,
                "max": 110,
            }
        },
    )
    await hass.async_block_till_done()

    async_fire_mqtt_message(hass, topic, "115.5")

    await hass.async_block_till_done()

    assert (
        "Invalid value for number.test_number: 115.5 (range 5.0 - 110.0)" in caplog.text
    )


@pytest.mark.parametrize(
    "service,topic,parameters,payload,template",
    [
        (
            SERVICE_SET_VALUE,
            "command_topic",
            {ATTR_VALUE: "45"},
            45,
            "command_template",
        ),
    ],
)
async def test_publishing_with_custom_encoding(
    hass,
    mqtt_mock,
    caplog,
    service,
    topic,
    parameters,
    payload,
    template,
):
    """Test publishing MQTT payload with different encoding."""
    domain = NUMBER_DOMAIN
    config = DEFAULT_CONFIG[domain]

    await help_test_publishing_with_custom_encoding(
        hass,
        mqtt_mock,
        caplog,
        domain,
        config,
        service,
        topic,
        parameters,
        payload,
        template,
    )


async def test_reloadable(hass, mqtt_mock, caplog, tmp_path):
    """Test reloading the MQTT platform."""
    domain = number.DOMAIN
    config = DEFAULT_CONFIG[domain]
    await help_test_reloadable(hass, mqtt_mock, caplog, tmp_path, domain, config)


async def test_reloadable_late(hass, mqtt_client_mock, caplog, tmp_path):
    """Test reloading the MQTT platform with late entry setup."""
    domain = number.DOMAIN
    config = DEFAULT_CONFIG[domain]
    await help_test_reloadable_late(hass, caplog, tmp_path, domain, config)


@pytest.mark.parametrize(
    "topic,value,attribute,attribute_value",
    [
        ("state_topic", "10", None, "10"),
        ("state_topic", "60", None, "60"),
    ],
)
async def test_encoding_subscribable_topics(
    hass, mqtt_mock, caplog, topic, value, attribute, attribute_value
):
    """Test handling of incoming encoded payload."""
    await help_test_encoding_subscribable_topics(
        hass,
        mqtt_mock,
        caplog,
        "number",
        DEFAULT_CONFIG["number"],
        topic,
        value,
        attribute,
        attribute_value,
    )
