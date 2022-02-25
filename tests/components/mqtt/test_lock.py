"""The tests for the MQTT lock platform."""
from unittest.mock import patch

import pytest

from homeassistant.components.lock import (
    DOMAIN as LOCK_DOMAIN,
    SERVICE_LOCK,
    SERVICE_OPEN,
    SERVICE_UNLOCK,
    STATE_LOCKED,
    STATE_UNLOCKED,
    SUPPORT_OPEN,
)
from homeassistant.components.mqtt.lock import MQTT_LOCK_ATTRIBUTES_BLOCKED
from homeassistant.const import (
    ATTR_ASSUMED_STATE,
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
)
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
    LOCK_DOMAIN: {"platform": "mqtt", "name": "test", "command_topic": "test-topic"}
}


async def test_controlling_state_via_topic(hass, mqtt_mock):
    """Test the controlling state via topic."""
    assert await async_setup_component(
        hass,
        LOCK_DOMAIN,
        {
            LOCK_DOMAIN: {
                "platform": "mqtt",
                "name": "test",
                "state_topic": "state-topic",
                "command_topic": "command-topic",
                "payload_lock": "LOCK",
                "payload_unlock": "UNLOCK",
                "state_locked": "LOCKED",
                "state_unlocked": "UNLOCKED",
            }
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("lock.test")
    assert state.state is STATE_UNLOCKED
    assert not state.attributes.get(ATTR_ASSUMED_STATE)
    assert not state.attributes.get(ATTR_SUPPORTED_FEATURES)

    async_fire_mqtt_message(hass, "state-topic", "LOCKED")

    state = hass.states.get("lock.test")
    assert state.state is STATE_LOCKED

    async_fire_mqtt_message(hass, "state-topic", "UNLOCKED")

    state = hass.states.get("lock.test")
    assert state.state is STATE_UNLOCKED


async def test_controlling_non_default_state_via_topic(hass, mqtt_mock):
    """Test the controlling state via topic."""
    assert await async_setup_component(
        hass,
        LOCK_DOMAIN,
        {
            LOCK_DOMAIN: {
                "platform": "mqtt",
                "name": "test",
                "state_topic": "state-topic",
                "command_topic": "command-topic",
                "payload_lock": "LOCK",
                "payload_unlock": "UNLOCK",
                "state_locked": "closed",
                "state_unlocked": "open",
            }
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("lock.test")
    assert state.state is STATE_UNLOCKED
    assert not state.attributes.get(ATTR_ASSUMED_STATE)

    async_fire_mqtt_message(hass, "state-topic", "closed")

    state = hass.states.get("lock.test")
    assert state.state is STATE_LOCKED

    async_fire_mqtt_message(hass, "state-topic", "open")

    state = hass.states.get("lock.test")
    assert state.state is STATE_UNLOCKED


async def test_controlling_state_via_topic_and_json_message(hass, mqtt_mock):
    """Test the controlling state via topic and JSON message."""
    assert await async_setup_component(
        hass,
        LOCK_DOMAIN,
        {
            LOCK_DOMAIN: {
                "platform": "mqtt",
                "name": "test",
                "state_topic": "state-topic",
                "command_topic": "command-topic",
                "payload_lock": "LOCK",
                "payload_unlock": "UNLOCK",
                "state_locked": "LOCKED",
                "state_unlocked": "UNLOCKED",
                "value_template": "{{ value_json.val }}",
            }
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("lock.test")
    assert state.state is STATE_UNLOCKED

    async_fire_mqtt_message(hass, "state-topic", '{"val":"LOCKED"}')

    state = hass.states.get("lock.test")
    assert state.state is STATE_LOCKED

    async_fire_mqtt_message(hass, "state-topic", '{"val":"UNLOCKED"}')

    state = hass.states.get("lock.test")
    assert state.state is STATE_UNLOCKED


async def test_controlling_non_default_state_via_topic_and_json_message(
    hass, mqtt_mock
):
    """Test the controlling state via topic and JSON message."""
    assert await async_setup_component(
        hass,
        LOCK_DOMAIN,
        {
            LOCK_DOMAIN: {
                "platform": "mqtt",
                "name": "test",
                "state_topic": "state-topic",
                "command_topic": "command-topic",
                "payload_lock": "LOCK",
                "payload_unlock": "UNLOCK",
                "state_locked": "closed",
                "state_unlocked": "open",
                "value_template": "{{ value_json.val }}",
            }
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("lock.test")
    assert state.state is STATE_UNLOCKED

    async_fire_mqtt_message(hass, "state-topic", '{"val":"closed"}')

    state = hass.states.get("lock.test")
    assert state.state is STATE_LOCKED

    async_fire_mqtt_message(hass, "state-topic", '{"val":"open"}')

    state = hass.states.get("lock.test")
    assert state.state is STATE_UNLOCKED


async def test_sending_mqtt_commands_and_optimistic(hass, mqtt_mock):
    """Test optimistic mode without state topic."""
    assert await async_setup_component(
        hass,
        LOCK_DOMAIN,
        {
            LOCK_DOMAIN: {
                "platform": "mqtt",
                "name": "test",
                "command_topic": "command-topic",
                "payload_lock": "LOCK",
                "payload_unlock": "UNLOCK",
                "state_locked": "LOCKED",
                "state_unlocked": "UNLOCKED",
            }
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("lock.test")
    assert state.state is STATE_UNLOCKED
    assert state.attributes.get(ATTR_ASSUMED_STATE)

    await hass.services.async_call(
        LOCK_DOMAIN, SERVICE_LOCK, {ATTR_ENTITY_ID: "lock.test"}, blocking=True
    )

    mqtt_mock.async_publish.assert_called_once_with("command-topic", "LOCK", 0, False)
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("lock.test")
    assert state.state is STATE_LOCKED
    assert state.attributes.get(ATTR_ASSUMED_STATE)

    await hass.services.async_call(
        LOCK_DOMAIN, SERVICE_UNLOCK, {ATTR_ENTITY_ID: "lock.test"}, blocking=True
    )

    mqtt_mock.async_publish.assert_called_once_with("command-topic", "UNLOCK", 0, False)
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("lock.test")
    assert state.state is STATE_UNLOCKED
    assert state.attributes.get(ATTR_ASSUMED_STATE)


async def test_sending_mqtt_commands_and_explicit_optimistic(hass, mqtt_mock):
    """Test optimistic mode without state topic."""
    assert await async_setup_component(
        hass,
        LOCK_DOMAIN,
        {
            LOCK_DOMAIN: {
                "platform": "mqtt",
                "name": "test",
                "state_topic": "state-topic",
                "command_topic": "command-topic",
                "payload_lock": "LOCK",
                "payload_unlock": "UNLOCK",
                "state_locked": "LOCKED",
                "state_unlocked": "UNLOCKED",
                "optimistic": True,
            }
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("lock.test")
    assert state.state is STATE_UNLOCKED
    assert state.attributes.get(ATTR_ASSUMED_STATE)

    await hass.services.async_call(
        LOCK_DOMAIN, SERVICE_LOCK, {ATTR_ENTITY_ID: "lock.test"}, blocking=True
    )

    mqtt_mock.async_publish.assert_called_once_with("command-topic", "LOCK", 0, False)
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("lock.test")
    assert state.state is STATE_LOCKED
    assert state.attributes.get(ATTR_ASSUMED_STATE)

    await hass.services.async_call(
        LOCK_DOMAIN, SERVICE_UNLOCK, {ATTR_ENTITY_ID: "lock.test"}, blocking=True
    )

    mqtt_mock.async_publish.assert_called_once_with("command-topic", "UNLOCK", 0, False)
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("lock.test")
    assert state.state is STATE_UNLOCKED
    assert state.attributes.get(ATTR_ASSUMED_STATE)


async def test_sending_mqtt_commands_support_open_and_optimistic(hass, mqtt_mock):
    """Test open function of the lock without state topic."""
    assert await async_setup_component(
        hass,
        LOCK_DOMAIN,
        {
            LOCK_DOMAIN: {
                "platform": "mqtt",
                "name": "test",
                "command_topic": "command-topic",
                "payload_lock": "LOCK",
                "payload_unlock": "UNLOCK",
                "payload_open": "OPEN",
                "state_locked": "LOCKED",
                "state_unlocked": "UNLOCKED",
            }
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("lock.test")
    assert state.state is STATE_UNLOCKED
    assert state.attributes.get(ATTR_ASSUMED_STATE)
    assert state.attributes.get(ATTR_SUPPORTED_FEATURES) == SUPPORT_OPEN

    await hass.services.async_call(
        LOCK_DOMAIN, SERVICE_LOCK, {ATTR_ENTITY_ID: "lock.test"}, blocking=True
    )

    mqtt_mock.async_publish.assert_called_once_with("command-topic", "LOCK", 0, False)
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("lock.test")
    assert state.state is STATE_LOCKED
    assert state.attributes.get(ATTR_ASSUMED_STATE)

    await hass.services.async_call(
        LOCK_DOMAIN, SERVICE_UNLOCK, {ATTR_ENTITY_ID: "lock.test"}, blocking=True
    )

    mqtt_mock.async_publish.assert_called_once_with("command-topic", "UNLOCK", 0, False)
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("lock.test")
    assert state.state is STATE_UNLOCKED
    assert state.attributes.get(ATTR_ASSUMED_STATE)

    await hass.services.async_call(
        LOCK_DOMAIN, SERVICE_OPEN, {ATTR_ENTITY_ID: "lock.test"}, blocking=True
    )

    mqtt_mock.async_publish.assert_called_once_with("command-topic", "OPEN", 0, False)
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("lock.test")
    assert state.state is STATE_UNLOCKED
    assert state.attributes.get(ATTR_ASSUMED_STATE)


async def test_sending_mqtt_commands_support_open_and_explicit_optimistic(
    hass, mqtt_mock
):
    """Test open function of the lock without state topic."""
    assert await async_setup_component(
        hass,
        LOCK_DOMAIN,
        {
            LOCK_DOMAIN: {
                "platform": "mqtt",
                "name": "test",
                "state_topic": "state-topic",
                "command_topic": "command-topic",
                "payload_lock": "LOCK",
                "payload_unlock": "UNLOCK",
                "payload_open": "OPEN",
                "state_locked": "LOCKED",
                "state_unlocked": "UNLOCKED",
                "optimistic": True,
            }
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("lock.test")
    assert state.state is STATE_UNLOCKED
    assert state.attributes.get(ATTR_ASSUMED_STATE)
    assert state.attributes.get(ATTR_SUPPORTED_FEATURES) == SUPPORT_OPEN

    await hass.services.async_call(
        LOCK_DOMAIN, SERVICE_LOCK, {ATTR_ENTITY_ID: "lock.test"}, blocking=True
    )

    mqtt_mock.async_publish.assert_called_once_with("command-topic", "LOCK", 0, False)
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("lock.test")
    assert state.state is STATE_LOCKED
    assert state.attributes.get(ATTR_ASSUMED_STATE)

    await hass.services.async_call(
        LOCK_DOMAIN, SERVICE_UNLOCK, {ATTR_ENTITY_ID: "lock.test"}, blocking=True
    )

    mqtt_mock.async_publish.assert_called_once_with("command-topic", "UNLOCK", 0, False)
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("lock.test")
    assert state.state is STATE_UNLOCKED
    assert state.attributes.get(ATTR_ASSUMED_STATE)

    await hass.services.async_call(
        LOCK_DOMAIN, SERVICE_OPEN, {ATTR_ENTITY_ID: "lock.test"}, blocking=True
    )

    mqtt_mock.async_publish.assert_called_once_with("command-topic", "OPEN", 0, False)
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("lock.test")
    assert state.state is STATE_UNLOCKED
    assert state.attributes.get(ATTR_ASSUMED_STATE)


async def test_availability_when_connection_lost(hass, mqtt_mock):
    """Test availability after MQTT disconnection."""
    await help_test_availability_when_connection_lost(
        hass, mqtt_mock, LOCK_DOMAIN, DEFAULT_CONFIG
    )


async def test_availability_without_topic(hass, mqtt_mock):
    """Test availability without defined availability topic."""
    await help_test_availability_without_topic(
        hass, mqtt_mock, LOCK_DOMAIN, DEFAULT_CONFIG
    )


async def test_default_availability_payload(hass, mqtt_mock):
    """Test availability by default payload with defined topic."""
    await help_test_default_availability_payload(
        hass, mqtt_mock, LOCK_DOMAIN, DEFAULT_CONFIG
    )


async def test_custom_availability_payload(hass, mqtt_mock):
    """Test availability by custom payload with defined topic."""
    await help_test_custom_availability_payload(
        hass, mqtt_mock, LOCK_DOMAIN, DEFAULT_CONFIG
    )


async def test_setting_attribute_via_mqtt_json_message(hass, mqtt_mock):
    """Test the setting of attribute via MQTT with JSON payload."""
    await help_test_setting_attribute_via_mqtt_json_message(
        hass, mqtt_mock, LOCK_DOMAIN, DEFAULT_CONFIG
    )


async def test_setting_blocked_attribute_via_mqtt_json_message(hass, mqtt_mock):
    """Test the setting of attribute via MQTT with JSON payload."""
    await help_test_setting_blocked_attribute_via_mqtt_json_message(
        hass, mqtt_mock, LOCK_DOMAIN, DEFAULT_CONFIG, MQTT_LOCK_ATTRIBUTES_BLOCKED
    )


async def test_setting_attribute_with_template(hass, mqtt_mock):
    """Test the setting of attribute via MQTT with JSON payload."""
    await help_test_setting_attribute_with_template(
        hass, mqtt_mock, LOCK_DOMAIN, DEFAULT_CONFIG
    )


async def test_update_with_json_attrs_not_dict(hass, mqtt_mock, caplog):
    """Test attributes get extracted from a JSON result."""
    await help_test_update_with_json_attrs_not_dict(
        hass, mqtt_mock, caplog, LOCK_DOMAIN, DEFAULT_CONFIG
    )


async def test_update_with_json_attrs_bad_json(hass, mqtt_mock, caplog):
    """Test attributes get extracted from a JSON result."""
    await help_test_update_with_json_attrs_bad_JSON(
        hass, mqtt_mock, caplog, LOCK_DOMAIN, DEFAULT_CONFIG
    )


async def test_discovery_update_attr(hass, mqtt_mock, caplog):
    """Test update of discovered MQTTAttributes."""
    await help_test_discovery_update_attr(
        hass, mqtt_mock, caplog, LOCK_DOMAIN, DEFAULT_CONFIG
    )


async def test_unique_id(hass, mqtt_mock):
    """Test unique id option only creates one lock per unique_id."""
    config = {
        LOCK_DOMAIN: [
            {
                "platform": "mqtt",
                "name": "Test 1",
                "state_topic": "test-topic",
                "command_topic": "test_topic",
                "unique_id": "TOTALLY_UNIQUE",
            },
            {
                "platform": "mqtt",
                "name": "Test 2",
                "state_topic": "test-topic",
                "command_topic": "test_topic",
                "unique_id": "TOTALLY_UNIQUE",
            },
        ]
    }
    await help_test_unique_id(hass, mqtt_mock, LOCK_DOMAIN, config)


async def test_discovery_removal_lock(hass, mqtt_mock, caplog):
    """Test removal of discovered lock."""
    data = '{ "name": "test",' '  "command_topic": "test_topic" }'
    await help_test_discovery_removal(hass, mqtt_mock, caplog, LOCK_DOMAIN, data)


async def test_discovery_update_lock(hass, mqtt_mock, caplog):
    """Test update of discovered lock."""
    config1 = {
        "name": "Beer",
        "state_topic": "test_topic",
        "command_topic": "command_topic",
        "availability_topic": "availability_topic1",
    }
    config2 = {
        "name": "Milk",
        "state_topic": "test_topic2",
        "command_topic": "command_topic",
        "availability_topic": "availability_topic2",
    }
    await help_test_discovery_update(
        hass, mqtt_mock, caplog, LOCK_DOMAIN, config1, config2
    )


async def test_discovery_update_unchanged_lock(hass, mqtt_mock, caplog):
    """Test update of discovered lock."""
    data1 = (
        '{ "name": "Beer",'
        '  "state_topic": "test_topic",'
        '  "command_topic": "command_topic" }'
    )
    with patch(
        "homeassistant.components.mqtt.lock.MqttLock.discovery_update"
    ) as discovery_update:
        await help_test_discovery_update_unchanged(
            hass, mqtt_mock, caplog, LOCK_DOMAIN, data1, discovery_update
        )


@pytest.mark.no_fail_on_log_exception
async def test_discovery_broken(hass, mqtt_mock, caplog):
    """Test handling of bad discovery message."""
    data1 = '{ "name": "Beer" }'
    data2 = '{ "name": "Milk",' '  "command_topic": "test_topic" }'
    await help_test_discovery_broken(hass, mqtt_mock, caplog, LOCK_DOMAIN, data1, data2)


async def test_entity_device_info_with_connection(hass, mqtt_mock):
    """Test MQTT lock device registry integration."""
    await help_test_entity_device_info_with_connection(
        hass, mqtt_mock, LOCK_DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_device_info_with_identifier(hass, mqtt_mock):
    """Test MQTT lock device registry integration."""
    await help_test_entity_device_info_with_identifier(
        hass, mqtt_mock, LOCK_DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_device_info_update(hass, mqtt_mock):
    """Test device registry update."""
    await help_test_entity_device_info_update(
        hass, mqtt_mock, LOCK_DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_device_info_remove(hass, mqtt_mock):
    """Test device registry remove."""
    await help_test_entity_device_info_remove(
        hass, mqtt_mock, LOCK_DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_id_update_subscriptions(hass, mqtt_mock):
    """Test MQTT subscriptions are managed when entity_id is updated."""
    await help_test_entity_id_update_subscriptions(
        hass, mqtt_mock, LOCK_DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_id_update_discovery_update(hass, mqtt_mock):
    """Test MQTT discovery update when entity_id is updated."""
    await help_test_entity_id_update_discovery_update(
        hass, mqtt_mock, LOCK_DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_debug_info_message(hass, mqtt_mock):
    """Test MQTT debug info."""
    await help_test_entity_debug_info_message(
        hass,
        mqtt_mock,
        LOCK_DOMAIN,
        DEFAULT_CONFIG,
        SERVICE_LOCK,
        command_payload="LOCK",
    )


@pytest.mark.parametrize(
    "service,topic,parameters,payload,template",
    [
        (
            SERVICE_LOCK,
            "command_topic",
            None,
            "LOCK",
            None,
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
    domain = LOCK_DOMAIN
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
    domain = LOCK_DOMAIN
    config = DEFAULT_CONFIG[domain]
    await help_test_reloadable(hass, mqtt_mock, caplog, tmp_path, domain, config)


async def test_reloadable_late(hass, mqtt_client_mock, caplog, tmp_path):
    """Test reloading the MQTT platform with late entry setup."""
    domain = LOCK_DOMAIN
    config = DEFAULT_CONFIG[domain]
    await help_test_reloadable_late(hass, caplog, tmp_path, domain, config)


@pytest.mark.parametrize(
    "topic,value,attribute,attribute_value",
    [
        ("state_topic", "LOCKED", None, "locked"),
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
        LOCK_DOMAIN,
        DEFAULT_CONFIG[LOCK_DOMAIN],
        topic,
        value,
        attribute,
        attribute_value,
    )
