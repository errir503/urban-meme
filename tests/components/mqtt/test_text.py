"""The tests for the MQTT text platform."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from homeassistant.components import mqtt, text
from homeassistant.const import (
    ATTR_ASSUMED_STATE,
    ATTR_ENTITY_ID,
    STATE_UNKNOWN,
    Platform,
)
from homeassistant.core import HomeAssistant
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
    help_test_setting_attribute_via_mqtt_json_message,
    help_test_setting_attribute_with_template,
    help_test_setting_blocked_attribute_via_mqtt_json_message,
    help_test_setup_manual_entity_from_yaml,
    help_test_unique_id,
    help_test_unload_config_entry_with_platform,
    help_test_update_with_json_attrs_bad_json,
    help_test_update_with_json_attrs_not_dict,
)

from tests.common import async_fire_mqtt_message

DEFAULT_CONFIG = {
    mqtt.DOMAIN: {text.DOMAIN: {"name": "test", "command_topic": "test-topic"}}
}


@pytest.fixture(autouse=True)
def text_platform_only():
    """Only setup the text platform to speed up tests."""
    with patch("homeassistant.components.mqtt.PLATFORMS", [Platform.TEXT]):
        yield


async def async_set_value(
    hass: HomeAssistant, entity_id: str, value: str | None
) -> None:
    """Set input_text to value."""
    await hass.services.async_call(
        text.DOMAIN,
        text.SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, text.ATTR_VALUE: value},
        blocking=True,
    )


async def test_controlling_state_via_topic(
    hass: HomeAssistant, mqtt_mock_entry_with_yaml_config
) -> None:
    """Test the controlling state via topic."""
    assert await async_setup_component(
        hass,
        mqtt.DOMAIN,
        {
            mqtt.DOMAIN: {
                text.DOMAIN: {
                    "name": "test",
                    "state_topic": "state-topic",
                    "command_topic": "command-topic",
                    "mode": "password",
                }
            }
        },
    )
    await hass.async_block_till_done()
    await mqtt_mock_entry_with_yaml_config()

    state = hass.states.get("text.test")
    assert state.state == STATE_UNKNOWN
    assert state.attributes[text.ATTR_MODE] == "password"
    assert not state.attributes.get(ATTR_ASSUMED_STATE)

    async_fire_mqtt_message(hass, "state-topic", "some state")

    state = hass.states.get("text.test")
    assert state.state == "some state"

    async_fire_mqtt_message(hass, "state-topic", "some other state")

    state = hass.states.get("text.test")
    assert state.state == "some other state"

    async_fire_mqtt_message(hass, "state-topic", "")

    state = hass.states.get("text.test")
    assert state.state == ""


async def test_controlling_validation_state_via_topic(
    hass, mqtt_mock_entry_with_yaml_config
) -> None:
    """Test the validation of a received state."""
    assert await async_setup_component(
        hass,
        mqtt.DOMAIN,
        {
            mqtt.DOMAIN: {
                text.DOMAIN: {
                    "name": "test",
                    "state_topic": "state-topic",
                    "command_topic": "command-topic",
                    "mode": "text",
                    "min": 2,
                    "max": 10,
                    "pattern": "(y|n)",
                }
            }
        },
    )
    await hass.async_block_till_done()
    await mqtt_mock_entry_with_yaml_config()

    state = hass.states.get("text.test")
    assert state.state == STATE_UNKNOWN
    assert state.attributes[text.ATTR_MODE] == "text"

    async_fire_mqtt_message(hass, "state-topic", "yes")
    state = hass.states.get("text.test")
    assert state.state == "yes"

    # test pattern error
    with pytest.raises(ValueError):
        async_fire_mqtt_message(hass, "state-topic", "other")
        await hass.async_block_till_done()
    state = hass.states.get("text.test")
    assert state.state == "yes"

    # test text size to large
    with pytest.raises(ValueError):
        async_fire_mqtt_message(hass, "state-topic", "yesyesyesyes")
        await hass.async_block_till_done()
    state = hass.states.get("text.test")
    assert state.state == "yes"

    # test text size to small
    with pytest.raises(ValueError):
        async_fire_mqtt_message(hass, "state-topic", "y")
        await hass.async_block_till_done()
    state = hass.states.get("text.test")
    assert state.state == "yes"

    async_fire_mqtt_message(hass, "state-topic", "no")
    await hass.async_block_till_done()
    state = hass.states.get("text.test")
    assert state.state == "no"


async def test_attribute_validation_max_greater_then_min(hass) -> None:
    """Test the validation of min and max configuration attributes."""
    assert not await async_setup_component(
        hass,
        mqtt.DOMAIN,
        {
            mqtt.DOMAIN: {
                text.DOMAIN: {
                    "name": "test",
                    "command_topic": "command-topic",
                    "min": 20,
                    "max": 10,
                }
            }
        },
    )


async def test_attribute_validation_max_not_greater_then_max_state_length(hass) -> None:
    """Test the max value of of max configuration attribute."""
    assert not await async_setup_component(
        hass,
        mqtt.DOMAIN,
        {
            mqtt.DOMAIN: {
                text.DOMAIN: {
                    "name": "test",
                    "command_topic": "command-topic",
                    "min": 20,
                    "max": 257,
                }
            }
        },
    )


async def test_sending_mqtt_commands_and_optimistic(
    hass, mqtt_mock_entry_with_yaml_config
):
    """Test the sending MQTT commands in optimistic mode."""
    assert await async_setup_component(
        hass,
        mqtt.DOMAIN,
        {
            mqtt.DOMAIN: {
                text.DOMAIN: {
                    "name": "test",
                    "command_topic": "command-topic",
                    "qos": "2",
                }
            }
        },
    )
    await hass.async_block_till_done()
    mqtt_mock = await mqtt_mock_entry_with_yaml_config()

    state = hass.states.get("text.test")
    assert state.state == STATE_UNKNOWN
    assert state.attributes.get(ATTR_ASSUMED_STATE)

    await async_set_value(hass, "text.test", "some other state")
    await hass.async_block_till_done()

    mqtt_mock.async_publish.assert_called_once_with(
        "command-topic", "some other state", 2, False
    )
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("text.test")
    assert state.state == "some other state"

    await async_set_value(hass, "text.test", "some new state")

    mqtt_mock.async_publish.assert_called_once_with(
        "command-topic", "some new state", 2, False
    )
    state = hass.states.get("text.test")
    assert state.state == "some new state"


async def test_set_text_validation(hass, mqtt_mock_entry_with_yaml_config):
    """Test the initial state in optimistic mode."""
    assert await async_setup_component(
        hass,
        mqtt.DOMAIN,
        {
            mqtt.DOMAIN: {
                text.DOMAIN: {
                    "name": "test",
                    "command_topic": "command-topic",
                    "mode": "text",
                    "min": 2,
                    "max": 10,
                    "pattern": "(y|n)",
                }
            }
        },
    )
    await hass.async_block_till_done()
    await mqtt_mock_entry_with_yaml_config()

    state = hass.states.get("text.test")
    assert state.state == STATE_UNKNOWN
    assert state.attributes.get(ATTR_ASSUMED_STATE)

    # text too long
    with pytest.raises(ValueError):
        await async_set_value(hass, "text.test", "yes yes yes yes")

    # text too short
    with pytest.raises(ValueError):
        await async_set_value(hass, "text.test", "y")

    # text not matching pattern
    with pytest.raises(ValueError):
        await async_set_value(hass, "text.test", "other")

    await async_set_value(hass, "text.test", "no")
    state = hass.states.get("text.test")
    assert state.state == "no"


async def test_availability_when_connection_lost(
    hass, mqtt_mock_entry_with_yaml_config
):
    """Test availability after MQTT disconnection."""
    await help_test_availability_when_connection_lost(
        hass, mqtt_mock_entry_with_yaml_config, text.DOMAIN, DEFAULT_CONFIG
    )


async def test_availability_without_topic(hass, mqtt_mock_entry_with_yaml_config):
    """Test availability without defined availability topic."""
    await help_test_availability_without_topic(
        hass, mqtt_mock_entry_with_yaml_config, text.DOMAIN, DEFAULT_CONFIG
    )


async def test_default_availability_payload(hass, mqtt_mock_entry_with_yaml_config):
    """Test availability by default payload with defined topic."""
    config = {
        mqtt.DOMAIN: {
            text.DOMAIN: {
                "name": "test",
                "state_topic": "state-topic",
                "command_topic": "command-topic",
            }
        }
    }

    await help_test_default_availability_payload(
        hass,
        mqtt_mock_entry_with_yaml_config,
        text.DOMAIN,
        config,
        True,
        "state-topic",
        "some state",
    )


async def test_custom_availability_payload(hass, mqtt_mock_entry_with_yaml_config):
    """Test availability by custom payload with defined topic."""
    config = {
        mqtt.DOMAIN: {
            text.DOMAIN: {
                "name": "test",
                "state_topic": "state-topic",
                "command_topic": "command-topic",
            }
        }
    }

    await help_test_custom_availability_payload(
        hass,
        mqtt_mock_entry_with_yaml_config,
        text.DOMAIN,
        config,
        True,
        "state-topic",
        "1",
    )


async def test_setting_attribute_via_mqtt_json_message(
    hass, mqtt_mock_entry_with_yaml_config
):
    """Test the setting of attribute via MQTT with JSON payload."""
    await help_test_setting_attribute_via_mqtt_json_message(
        hass, mqtt_mock_entry_with_yaml_config, text.DOMAIN, DEFAULT_CONFIG
    )


async def test_setting_blocked_attribute_via_mqtt_json_message(
    hass, mqtt_mock_entry_no_yaml_config
):
    """Test the setting of attribute via MQTT with JSON payload."""
    await help_test_setting_blocked_attribute_via_mqtt_json_message(
        hass, mqtt_mock_entry_no_yaml_config, text.DOMAIN, DEFAULT_CONFIG, {}
    )


async def test_setting_attribute_with_template(hass, mqtt_mock_entry_with_yaml_config):
    """Test the setting of attribute via MQTT with JSON payload."""
    await help_test_setting_attribute_with_template(
        hass, mqtt_mock_entry_with_yaml_config, text.DOMAIN, DEFAULT_CONFIG
    )


async def test_update_with_json_attrs_not_dict(
    hass, mqtt_mock_entry_with_yaml_config, caplog
):
    """Test attributes get extracted from a JSON result."""
    await help_test_update_with_json_attrs_not_dict(
        hass,
        mqtt_mock_entry_with_yaml_config,
        caplog,
        text.DOMAIN,
        DEFAULT_CONFIG,
    )


async def test_update_with_json_attrs_bad_json(
    hass, mqtt_mock_entry_with_yaml_config, caplog
):
    """Test attributes get extracted from a JSON result."""
    await help_test_update_with_json_attrs_bad_json(
        hass,
        mqtt_mock_entry_with_yaml_config,
        caplog,
        text.DOMAIN,
        DEFAULT_CONFIG,
    )


async def test_discovery_update_attr(hass, mqtt_mock_entry_no_yaml_config, caplog):
    """Test update of discovered MQTTAttributes."""
    await help_test_discovery_update_attr(
        hass,
        mqtt_mock_entry_no_yaml_config,
        caplog,
        text.DOMAIN,
        DEFAULT_CONFIG,
    )


async def test_unique_id(hass, mqtt_mock_entry_with_yaml_config):
    """Test unique id option only creates one text per unique_id."""
    config = {
        mqtt.DOMAIN: {
            text.DOMAIN: [
                {
                    "name": "Test 1",
                    "state_topic": "test-topic",
                    "command_topic": "command-topic",
                    "unique_id": "TOTALLY_UNIQUE",
                },
                {
                    "name": "Test 2",
                    "state_topic": "test-topic",
                    "command_topic": "command-topic",
                    "unique_id": "TOTALLY_UNIQUE",
                },
            ]
        }
    }
    await help_test_unique_id(
        hass, mqtt_mock_entry_with_yaml_config, text.DOMAIN, config
    )


async def test_discovery_removal_text(hass, mqtt_mock_entry_no_yaml_config, caplog):
    """Test removal of discovered text entity."""
    data = (
        '{ "name": "test",'
        '  "state_topic": "test_topic",'
        '  "command_topic": "test_topic" }'
    )
    await help_test_discovery_removal(
        hass, mqtt_mock_entry_no_yaml_config, caplog, text.DOMAIN, data
    )


async def test_discovery_text_update(hass, mqtt_mock_entry_no_yaml_config, caplog):
    """Test update of discovered text entity."""
    config1 = {
        "name": "Beer",
        "command_topic": "command-topic",
        "state_topic": "state-topic",
    }
    config2 = {
        "name": "Milk",
        "command_topic": "command-topic",
        "state_topic": "state-topic",
    }

    await help_test_discovery_update(
        hass, mqtt_mock_entry_no_yaml_config, caplog, text.DOMAIN, config1, config2
    )


async def test_discovery_update_unchanged_update(
    hass, mqtt_mock_entry_no_yaml_config, caplog
):
    """Test update of discovered update."""
    data1 = '{ "name": "Beer", "state_topic": "text-topic", "command_topic": "command-topic"}'
    with patch(
        "homeassistant.components.mqtt.text.MqttTextEntity.discovery_update"
    ) as discovery_update:
        await help_test_discovery_update_unchanged(
            hass,
            mqtt_mock_entry_no_yaml_config,
            caplog,
            text.DOMAIN,
            data1,
            discovery_update,
        )


async def test_discovery_update_text(hass, mqtt_mock_entry_no_yaml_config, caplog):
    """Test update of discovered text entity."""
    config1 = {"name": "Beer", "command_topic": "cmd-topic1"}
    config2 = {"name": "Milk", "command_topic": "cmd-topic2"}
    await help_test_discovery_update(
        hass, mqtt_mock_entry_no_yaml_config, caplog, text.DOMAIN, config1, config2
    )


async def test_discovery_update_unchanged_climate(
    hass, mqtt_mock_entry_no_yaml_config, caplog
):
    """Test update of discovered text entity."""
    data1 = '{ "name": "Beer", "command_topic": "cmd-topic" }'
    with patch(
        "homeassistant.components.mqtt.text.MqttTextEntity.discovery_update"
    ) as discovery_update:
        await help_test_discovery_update_unchanged(
            hass,
            mqtt_mock_entry_no_yaml_config,
            caplog,
            text.DOMAIN,
            data1,
            discovery_update,
        )


@pytest.mark.no_fail_on_log_exception
async def test_discovery_broken(hass, mqtt_mock_entry_no_yaml_config, caplog):
    """Test handling of bad discovery message."""
    data1 = '{ "name": "Beer" }'
    data2 = (
        '{ "name": "Milk",'
        '  "state_topic": "test_topic",'
        '  "command_topic": "test_topic" }'
    )
    await help_test_discovery_broken(
        hass, mqtt_mock_entry_no_yaml_config, caplog, text.DOMAIN, data1, data2
    )


async def test_entity_device_info_with_connection(hass, mqtt_mock_entry_no_yaml_config):
    """Test MQTT text device registry integration."""
    await help_test_entity_device_info_with_connection(
        hass, mqtt_mock_entry_no_yaml_config, text.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_device_info_with_identifier(hass, mqtt_mock_entry_no_yaml_config):
    """Test MQTT text device registry integration."""
    await help_test_entity_device_info_with_identifier(
        hass, mqtt_mock_entry_no_yaml_config, text.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_device_info_update(hass, mqtt_mock_entry_no_yaml_config):
    """Test device registry update."""
    await help_test_entity_device_info_update(
        hass, mqtt_mock_entry_no_yaml_config, text.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_device_info_remove(hass, mqtt_mock_entry_no_yaml_config):
    """Test device registry remove."""
    await help_test_entity_device_info_remove(
        hass, mqtt_mock_entry_no_yaml_config, text.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_id_update_subscriptions(hass, mqtt_mock_entry_with_yaml_config):
    """Test MQTT subscriptions are managed when entity_id is updated."""
    await help_test_entity_id_update_subscriptions(
        hass, mqtt_mock_entry_with_yaml_config, text.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_id_update_discovery_update(hass, mqtt_mock_entry_no_yaml_config):
    """Test MQTT discovery update when entity_id is updated."""
    await help_test_entity_id_update_discovery_update(
        hass, mqtt_mock_entry_no_yaml_config, text.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_debug_info_message(hass, mqtt_mock_entry_no_yaml_config):
    """Test MQTT debug info."""
    await help_test_entity_debug_info_message(
        hass, mqtt_mock_entry_no_yaml_config, text.DOMAIN, DEFAULT_CONFIG, None
    )


@pytest.mark.parametrize(
    "service,topic,parameters,payload,template",
    [
        (
            text.SERVICE_SET_VALUE,
            "command_topic",
            {text.ATTR_VALUE: "some text"},
            "some text",
            "command_template",
        ),
    ],
)
async def test_publishing_with_custom_encoding(
    hass,
    mqtt_mock_entry_with_yaml_config,
    caplog,
    service,
    topic,
    parameters,
    payload,
    template,
):
    """Test publishing MQTT payload with different encoding."""
    domain = text.DOMAIN
    config = DEFAULT_CONFIG

    await help_test_publishing_with_custom_encoding(
        hass,
        mqtt_mock_entry_with_yaml_config,
        caplog,
        domain,
        config,
        service,
        topic,
        parameters,
        payload,
        template,
    )


async def test_reloadable(hass, mqtt_mock_entry_with_yaml_config, caplog, tmp_path):
    """Test reloading the MQTT platform."""
    domain = text.DOMAIN
    config = DEFAULT_CONFIG
    await help_test_reloadable(
        hass, mqtt_mock_entry_with_yaml_config, caplog, tmp_path, domain, config
    )


@pytest.mark.parametrize(
    "topic,value,attribute,attribute_value",
    [
        ("state_topic", "some text", None, "some text"),
    ],
)
async def test_encoding_subscribable_topics(
    hass,
    mqtt_mock_entry_with_yaml_config,
    caplog,
    topic,
    value,
    attribute,
    attribute_value,
):
    """Test handling of incoming encoded payload."""
    await help_test_encoding_subscribable_topics(
        hass,
        mqtt_mock_entry_with_yaml_config,
        caplog,
        text.DOMAIN,
        DEFAULT_CONFIG[mqtt.DOMAIN][text.DOMAIN],
        topic,
        value,
        attribute,
        attribute_value,
    )


async def test_setup_manual_entity_from_yaml(hass):
    """Test setup manual configured MQTT entity."""
    platform = text.DOMAIN
    await help_test_setup_manual_entity_from_yaml(hass, DEFAULT_CONFIG)
    assert hass.states.get(f"{platform}.test")


async def test_unload_entry(hass, mqtt_mock_entry_with_yaml_config, tmp_path):
    """Test unloading the config entry."""
    domain = text.DOMAIN
    config = DEFAULT_CONFIG
    await help_test_unload_config_entry_with_platform(
        hass, mqtt_mock_entry_with_yaml_config, tmp_path, domain, config
    )
