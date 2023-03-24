"""The tests the MQTT alarm control panel component."""
import copy
import json
from typing import Any
from unittest.mock import patch

import pytest

from homeassistant.components import alarm_control_panel, mqtt
from homeassistant.components.mqtt.alarm_control_panel import (
    MQTT_ALARM_ATTRIBUTES_BLOCKED,
)
from homeassistant.components.mqtt.models import PublishPayloadType
from homeassistant.const import (
    ATTR_CODE,
    ATTR_ENTITY_ID,
    SERVICE_ALARM_ARM_AWAY,
    SERVICE_ALARM_ARM_CUSTOM_BYPASS,
    SERVICE_ALARM_ARM_HOME,
    SERVICE_ALARM_ARM_NIGHT,
    SERVICE_ALARM_ARM_VACATION,
    SERVICE_ALARM_DISARM,
    SERVICE_ALARM_TRIGGER,
    STATE_ALARM_ARMED_AWAY,
    STATE_ALARM_ARMED_CUSTOM_BYPASS,
    STATE_ALARM_ARMED_HOME,
    STATE_ALARM_ARMED_NIGHT,
    STATE_ALARM_ARMED_VACATION,
    STATE_ALARM_ARMING,
    STATE_ALARM_DISARMED,
    STATE_ALARM_DISARMING,
    STATE_ALARM_PENDING,
    STATE_ALARM_TRIGGERED,
    STATE_UNKNOWN,
    Platform,
)
from homeassistant.core import HomeAssistant

from .test_common import (
    help_custom_config,
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
    help_test_unique_id,
    help_test_unload_config_entry_with_platform,
    help_test_update_with_json_attrs_bad_json,
    help_test_update_with_json_attrs_not_dict,
    help_test_validate_platform_config,
)

from tests.common import async_fire_mqtt_message
from tests.components.alarm_control_panel import common
from tests.typing import MqttMockHAClientGenerator, MqttMockPahoClient

CODE_NUMBER = "1234"
CODE_TEXT = "HELLO_CODE"

DEFAULT_CONFIG = {
    mqtt.DOMAIN: {
        alarm_control_panel.DOMAIN: {
            "name": "test",
            "state_topic": "alarm/state",
            "command_topic": "alarm/command",
        }
    }
}

DEFAULT_CONFIG_CODE = {
    mqtt.DOMAIN: {
        alarm_control_panel.DOMAIN: {
            "name": "test",
            "state_topic": "alarm/state",
            "command_topic": "alarm/command",
            "code": "0123",
            "code_arm_required": True,
        }
    }
}

DEFAULT_CONFIG_REMOTE_CODE = {
    mqtt.DOMAIN: {
        alarm_control_panel.DOMAIN: {
            "name": "test",
            "state_topic": "alarm/state",
            "command_topic": "alarm/command",
            "code": "REMOTE_CODE",
            "code_arm_required": True,
        }
    }
}

DEFAULT_CONFIG_REMOTE_CODE_TEXT = {
    mqtt.DOMAIN: {
        alarm_control_panel.DOMAIN: {
            "name": "test",
            "state_topic": "alarm/state",
            "command_topic": "alarm/command",
            "code": "REMOTE_CODE_TEXT",
            "code_arm_required": True,
        }
    }
}


@pytest.fixture(autouse=True)
def alarm_control_panel_platform_only():
    """Only setup the alarm_control_panel platform to speed up tests."""
    with patch(
        "homeassistant.components.mqtt.PLATFORMS", [Platform.ALARM_CONTROL_PANEL]
    ):
        yield


@pytest.mark.parametrize(
    ("config", "valid"),
    [
        (
            {
                mqtt.DOMAIN: {
                    alarm_control_panel.DOMAIN: {
                        "name": "test",
                        "command_topic": "alarm/command",
                    }
                }
            },
            False,
        ),
        (
            {
                mqtt.DOMAIN: {
                    alarm_control_panel.DOMAIN: {
                        "name": "test",
                        "state_topic": "alarm/state",
                    }
                }
            },
            False,
        ),
        (
            {
                mqtt.DOMAIN: {
                    alarm_control_panel.DOMAIN: {
                        "name": "test",
                        "command_topic": "alarm/command",
                        "state_topic": "alarm/state",
                    }
                }
            },
            True,
        ),
    ],
)
async def test_fail_setup_without_state_or_command_topic(
    hass: HomeAssistant, config, valid
) -> None:
    """Test for failing setup with no state or command topic."""
    assert help_test_validate_platform_config(hass, config) == valid


@pytest.mark.parametrize("hass_config", [DEFAULT_CONFIG])
async def test_update_state_via_state_topic(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test updating with via state topic."""
    await mqtt_mock_entry_no_yaml_config()
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    for state in (
        STATE_ALARM_DISARMED,
        STATE_ALARM_ARMED_HOME,
        STATE_ALARM_ARMED_AWAY,
        STATE_ALARM_ARMED_NIGHT,
        STATE_ALARM_ARMED_VACATION,
        STATE_ALARM_ARMED_CUSTOM_BYPASS,
        STATE_ALARM_PENDING,
        STATE_ALARM_ARMING,
        STATE_ALARM_DISARMING,
        STATE_ALARM_TRIGGERED,
    ):
        async_fire_mqtt_message(hass, "alarm/state", state)
        assert hass.states.get(entity_id).state == state


@pytest.mark.parametrize("hass_config", [DEFAULT_CONFIG])
async def test_ignore_update_state_if_unknown_via_state_topic(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test ignoring updates via state topic."""
    await mqtt_mock_entry_no_yaml_config()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    async_fire_mqtt_message(hass, "alarm/state", "unsupported state")
    assert hass.states.get(entity_id).state == STATE_UNKNOWN


@pytest.mark.parametrize(
    ("hass_config", "service", "payload"),
    [
        (DEFAULT_CONFIG, SERVICE_ALARM_ARM_HOME, "ARM_HOME"),
        (DEFAULT_CONFIG, SERVICE_ALARM_ARM_AWAY, "ARM_AWAY"),
        (DEFAULT_CONFIG, SERVICE_ALARM_ARM_NIGHT, "ARM_NIGHT"),
        (DEFAULT_CONFIG, SERVICE_ALARM_ARM_VACATION, "ARM_VACATION"),
        (DEFAULT_CONFIG, SERVICE_ALARM_ARM_CUSTOM_BYPASS, "ARM_CUSTOM_BYPASS"),
        (DEFAULT_CONFIG, SERVICE_ALARM_DISARM, "DISARM"),
        (DEFAULT_CONFIG, SERVICE_ALARM_TRIGGER, "TRIGGER"),
    ],
)
async def test_publish_mqtt_no_code(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    service,
    payload,
) -> None:
    """Test publishing of MQTT messages when no code is configured."""
    mqtt_mock = await mqtt_mock_entry_no_yaml_config()

    await hass.services.async_call(
        alarm_control_panel.DOMAIN,
        service,
        {ATTR_ENTITY_ID: "alarm_control_panel.test"},
        blocking=True,
    )

    mqtt_mock.async_publish.assert_called_once_with("alarm/command", payload, 0, False)


@pytest.mark.parametrize(
    ("hass_config", "service", "payload"),
    [
        (DEFAULT_CONFIG_CODE, SERVICE_ALARM_ARM_HOME, "ARM_HOME"),
        (DEFAULT_CONFIG_CODE, SERVICE_ALARM_ARM_AWAY, "ARM_AWAY"),
        (DEFAULT_CONFIG_CODE, SERVICE_ALARM_ARM_NIGHT, "ARM_NIGHT"),
        (DEFAULT_CONFIG_CODE, SERVICE_ALARM_ARM_VACATION, "ARM_VACATION"),
        (DEFAULT_CONFIG_CODE, SERVICE_ALARM_ARM_CUSTOM_BYPASS, "ARM_CUSTOM_BYPASS"),
        (DEFAULT_CONFIG_CODE, SERVICE_ALARM_DISARM, "DISARM"),
        (DEFAULT_CONFIG_CODE, SERVICE_ALARM_TRIGGER, "TRIGGER"),
    ],
)
async def test_publish_mqtt_with_code(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    service,
    payload,
) -> None:
    """Test publishing of MQTT messages when code is configured."""
    mqtt_mock = await mqtt_mock_entry_no_yaml_config()
    call_count = mqtt_mock.async_publish.call_count

    # No code provided, should not publish
    await hass.services.async_call(
        alarm_control_panel.DOMAIN,
        service,
        {ATTR_ENTITY_ID: "alarm_control_panel.test"},
        blocking=True,
    )
    assert mqtt_mock.async_publish.call_count == call_count

    # Wrong code provided, should not publish
    await hass.services.async_call(
        alarm_control_panel.DOMAIN,
        service,
        {ATTR_ENTITY_ID: "alarm_control_panel.test", ATTR_CODE: "abcd"},
        blocking=True,
    )
    assert mqtt_mock.async_publish.call_count == call_count

    # Correct code provided, should publish
    await hass.services.async_call(
        alarm_control_panel.DOMAIN,
        service,
        {ATTR_ENTITY_ID: "alarm_control_panel.test", ATTR_CODE: "0123"},
        blocking=True,
    )
    mqtt_mock.async_publish.assert_called_once_with("alarm/command", payload, 0, False)


@pytest.mark.parametrize(
    ("hass_config", "service", "payload"),
    [
        (DEFAULT_CONFIG_REMOTE_CODE, SERVICE_ALARM_ARM_HOME, "ARM_HOME"),
        (DEFAULT_CONFIG_REMOTE_CODE, SERVICE_ALARM_ARM_AWAY, "ARM_AWAY"),
        (DEFAULT_CONFIG_REMOTE_CODE, SERVICE_ALARM_ARM_NIGHT, "ARM_NIGHT"),
        (DEFAULT_CONFIG_REMOTE_CODE, SERVICE_ALARM_ARM_VACATION, "ARM_VACATION"),
        (
            DEFAULT_CONFIG_REMOTE_CODE,
            SERVICE_ALARM_ARM_CUSTOM_BYPASS,
            "ARM_CUSTOM_BYPASS",
        ),
        (DEFAULT_CONFIG_REMOTE_CODE, SERVICE_ALARM_DISARM, "DISARM"),
        (DEFAULT_CONFIG_REMOTE_CODE, SERVICE_ALARM_TRIGGER, "TRIGGER"),
    ],
)
async def test_publish_mqtt_with_remote_code(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    service,
    payload,
) -> None:
    """Test publishing of MQTT messages when remode code is configured."""
    mqtt_mock = await mqtt_mock_entry_no_yaml_config()
    call_count = mqtt_mock.async_publish.call_count

    # No code provided, should not publish
    await hass.services.async_call(
        alarm_control_panel.DOMAIN,
        service,
        {ATTR_ENTITY_ID: "alarm_control_panel.test"},
        blocking=True,
    )
    assert mqtt_mock.async_publish.call_count == call_count

    # Any code numbered  provided, should publish
    await hass.services.async_call(
        alarm_control_panel.DOMAIN,
        service,
        {ATTR_ENTITY_ID: "alarm_control_panel.test", ATTR_CODE: "1234"},
        blocking=True,
    )
    mqtt_mock.async_publish.assert_called_once_with("alarm/command", payload, 0, False)


@pytest.mark.parametrize(
    ("hass_config", "service", "payload"),
    [
        (DEFAULT_CONFIG_REMOTE_CODE_TEXT, SERVICE_ALARM_ARM_HOME, "ARM_HOME"),
        (DEFAULT_CONFIG_REMOTE_CODE_TEXT, SERVICE_ALARM_ARM_AWAY, "ARM_AWAY"),
        (DEFAULT_CONFIG_REMOTE_CODE_TEXT, SERVICE_ALARM_ARM_NIGHT, "ARM_NIGHT"),
        (DEFAULT_CONFIG_REMOTE_CODE_TEXT, SERVICE_ALARM_ARM_VACATION, "ARM_VACATION"),
        (
            DEFAULT_CONFIG_REMOTE_CODE_TEXT,
            SERVICE_ALARM_ARM_CUSTOM_BYPASS,
            "ARM_CUSTOM_BYPASS",
        ),
        (DEFAULT_CONFIG_REMOTE_CODE_TEXT, SERVICE_ALARM_DISARM, "DISARM"),
        (DEFAULT_CONFIG_REMOTE_CODE_TEXT, SERVICE_ALARM_TRIGGER, "TRIGGER"),
    ],
)
async def test_publish_mqtt_with_remote_code_text(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    service: str,
    payload: str,
) -> None:
    """Test publishing of MQTT messages when remote text code is configured."""
    mqtt_mock = await mqtt_mock_entry_no_yaml_config()
    call_count = mqtt_mock.async_publish.call_count

    # No code provided, should not publish
    await hass.services.async_call(
        alarm_control_panel.DOMAIN,
        service,
        {ATTR_ENTITY_ID: "alarm_control_panel.test"},
        blocking=True,
    )
    assert mqtt_mock.async_publish.call_count == call_count

    # Any code numbered  provided, should publish
    await hass.services.async_call(
        alarm_control_panel.DOMAIN,
        service,
        {ATTR_ENTITY_ID: "alarm_control_panel.test", ATTR_CODE: "any_code"},
        blocking=True,
    )
    mqtt_mock.async_publish.assert_called_once_with("alarm/command", payload, 0, False)


@pytest.mark.parametrize(
    ("hass_config", "service", "payload"),
    [
        (
            help_custom_config(
                alarm_control_panel.DOMAIN,
                DEFAULT_CONFIG_CODE,
                ({"code_arm_required": False},),
            ),
            SERVICE_ALARM_ARM_HOME,
            "ARM_HOME",
        ),
        (
            help_custom_config(
                alarm_control_panel.DOMAIN,
                DEFAULT_CONFIG_CODE,
                ({"code_arm_required": False},),
            ),
            SERVICE_ALARM_ARM_AWAY,
            "ARM_AWAY",
        ),
        (
            help_custom_config(
                alarm_control_panel.DOMAIN,
                DEFAULT_CONFIG_CODE,
                ({"code_arm_required": False},),
            ),
            SERVICE_ALARM_ARM_NIGHT,
            "ARM_NIGHT",
        ),
        (
            help_custom_config(
                alarm_control_panel.DOMAIN,
                DEFAULT_CONFIG_CODE,
                ({"code_arm_required": False},),
            ),
            SERVICE_ALARM_ARM_VACATION,
            "ARM_VACATION",
        ),
        (
            help_custom_config(
                alarm_control_panel.DOMAIN,
                DEFAULT_CONFIG_CODE,
                ({"code_arm_required": False},),
            ),
            SERVICE_ALARM_ARM_CUSTOM_BYPASS,
            "ARM_CUSTOM_BYPASS",
        ),
        (
            help_custom_config(
                alarm_control_panel.DOMAIN,
                DEFAULT_CONFIG_CODE,
                ({"code_disarm_required": False},),
            ),
            SERVICE_ALARM_DISARM,
            "DISARM",
        ),
        (
            help_custom_config(
                alarm_control_panel.DOMAIN,
                DEFAULT_CONFIG_CODE,
                ({"code_trigger_required": False},),
            ),
            SERVICE_ALARM_TRIGGER,
            "TRIGGER",
        ),
    ],
)
async def test_publish_mqtt_with_code_required_false(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    service: str,
    payload: str,
) -> None:
    """Test publishing of MQTT messages when code is configured.

    code_arm_required = False / code_disarm_required = False /
    code_trigger_required = False
    """
    mqtt_mock = await mqtt_mock_entry_no_yaml_config()

    # No code provided, should publish
    await hass.services.async_call(
        alarm_control_panel.DOMAIN,
        service,
        {ATTR_ENTITY_ID: "alarm_control_panel.test"},
        blocking=True,
    )
    mqtt_mock.async_publish.assert_called_once_with("alarm/command", payload, 0, False)
    mqtt_mock.reset_mock()

    # Wrong code provided, should publish
    await hass.services.async_call(
        alarm_control_panel.DOMAIN,
        service,
        {ATTR_ENTITY_ID: "alarm_control_panel.test", ATTR_CODE: "abcd"},
        blocking=True,
    )
    mqtt_mock.async_publish.assert_called_once_with("alarm/command", payload, 0, False)
    mqtt_mock.reset_mock()

    # Correct code provided, should publish
    await hass.services.async_call(
        alarm_control_panel.DOMAIN,
        service,
        {ATTR_ENTITY_ID: "alarm_control_panel.test", ATTR_CODE: "0123"},
        blocking=True,
    )
    mqtt_mock.async_publish.assert_called_once_with("alarm/command", payload, 0, False)
    mqtt_mock.reset_mock()


@pytest.mark.parametrize(
    "hass_config",
    [
        help_custom_config(
            alarm_control_panel.DOMAIN,
            DEFAULT_CONFIG_CODE,
            (
                {
                    "code": "0123",
                    "command_template": '{"action":"{{ action }}","code":"{{ code }}"}',
                },
            ),
        )
    ],
)
async def test_disarm_publishes_mqtt_with_template(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test publishing of MQTT messages while disarmed.

    When command_template set to output json
    """
    mqtt_mock = await mqtt_mock_entry_no_yaml_config()

    await common.async_alarm_disarm(hass, "0123")
    mqtt_mock.async_publish.assert_called_once_with(
        "alarm/command", '{"action":"DISARM","code":"0123"}', 0, False
    )


@pytest.mark.parametrize(
    "hass_config",
    [
        {
            mqtt.DOMAIN: {
                alarm_control_panel.DOMAIN: {
                    "name": "test",
                    "command_topic": "test-topic",
                    "state_topic": "test-topic",
                    "value_template": "\
                {% if (value | int)  == 100 %}\
                  armed_away\
                {% else %}\
                   disarmed\
                {% endif %}",
                }
            }
        }
    ],
)
async def test_update_state_via_state_topic_template(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test updating with template_value via state topic."""
    await mqtt_mock_entry_no_yaml_config()

    state = hass.states.get("alarm_control_panel.test")
    assert state.state == STATE_UNKNOWN

    async_fire_mqtt_message(hass, "test-topic", "100")

    state = hass.states.get("alarm_control_panel.test")
    assert state.state == STATE_ALARM_ARMED_AWAY


@pytest.mark.parametrize(
    "hass_config",
    [
        help_custom_config(
            alarm_control_panel.DOMAIN, DEFAULT_CONFIG, ({"code": CODE_NUMBER},)
        )
    ],
)
async def test_attributes_code_number(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test attributes which are not supported by the vacuum."""
    await mqtt_mock_entry_no_yaml_config()

    state = hass.states.get("alarm_control_panel.test")
    assert (
        state.attributes.get(alarm_control_panel.ATTR_CODE_FORMAT)
        == alarm_control_panel.CodeFormat.NUMBER
    )


@pytest.mark.parametrize(
    "hass_config",
    [
        help_custom_config(
            alarm_control_panel.DOMAIN,
            DEFAULT_CONFIG_REMOTE_CODE,
            ({"code": "REMOTE_CODE"},),
        )
    ],
)
async def test_attributes_remote_code_number(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test attributes which are not supported by the vacuum."""
    await mqtt_mock_entry_no_yaml_config()

    state = hass.states.get("alarm_control_panel.test")
    assert (
        state.attributes.get(alarm_control_panel.ATTR_CODE_FORMAT)
        == alarm_control_panel.CodeFormat.NUMBER
    )


@pytest.mark.parametrize(
    "hass_config",
    [
        help_custom_config(
            alarm_control_panel.DOMAIN, DEFAULT_CONFIG, ({"code": CODE_TEXT},)
        )
    ],
)
async def test_attributes_code_text(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test attributes which are not supported by the vacuum."""
    await mqtt_mock_entry_no_yaml_config()

    state = hass.states.get("alarm_control_panel.test")
    assert (
        state.attributes.get(alarm_control_panel.ATTR_CODE_FORMAT)
        == alarm_control_panel.CodeFormat.TEXT
    )


@pytest.mark.parametrize("hass_config", [DEFAULT_CONFIG_CODE])
async def test_availability_when_connection_lost(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test availability after MQTT disconnection."""
    await help_test_availability_when_connection_lost(
        hass, mqtt_mock_entry_no_yaml_config, alarm_control_panel.DOMAIN
    )


@pytest.mark.parametrize("hass_config", [DEFAULT_CONFIG_CODE])
async def test_availability_without_topic(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test availability without defined availability topic."""
    await help_test_availability_without_topic(
        hass,
        mqtt_mock_entry_no_yaml_config,
        alarm_control_panel.DOMAIN,
        DEFAULT_CONFIG_CODE,
    )


async def test_default_availability_payload(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test availability by default payload with defined topic."""
    await help_test_default_availability_payload(
        hass,
        mqtt_mock_entry_no_yaml_config,
        alarm_control_panel.DOMAIN,
        DEFAULT_CONFIG_CODE,
    )


async def test_custom_availability_payload(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test availability by custom payload with defined topic."""
    await help_test_custom_availability_payload(
        hass,
        mqtt_mock_entry_no_yaml_config,
        alarm_control_panel.DOMAIN,
        DEFAULT_CONFIG,
    )


async def test_setting_attribute_via_mqtt_json_message(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test the setting of attribute via MQTT with JSON payload."""
    await help_test_setting_attribute_via_mqtt_json_message(
        hass,
        mqtt_mock_entry_no_yaml_config,
        alarm_control_panel.DOMAIN,
        DEFAULT_CONFIG,
    )


async def test_setting_blocked_attribute_via_mqtt_json_message(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test the setting of attribute via MQTT with JSON payload."""
    await help_test_setting_blocked_attribute_via_mqtt_json_message(
        hass,
        mqtt_mock_entry_no_yaml_config,
        alarm_control_panel.DOMAIN,
        DEFAULT_CONFIG,
        MQTT_ALARM_ATTRIBUTES_BLOCKED,
    )


async def test_setting_attribute_with_template(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test the setting of attribute via MQTT with JSON payload."""
    await help_test_setting_attribute_with_template(
        hass,
        mqtt_mock_entry_no_yaml_config,
        alarm_control_panel.DOMAIN,
        DEFAULT_CONFIG,
    )


async def test_update_with_json_attrs_not_dict(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test attributes get extracted from a JSON result."""
    await help_test_update_with_json_attrs_not_dict(
        hass,
        mqtt_mock_entry_no_yaml_config,
        caplog,
        alarm_control_panel.DOMAIN,
        DEFAULT_CONFIG,
    )


async def test_update_with_json_attrs_bad_json(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test attributes get extracted from a JSON result."""
    await help_test_update_with_json_attrs_bad_json(
        hass,
        mqtt_mock_entry_no_yaml_config,
        caplog,
        alarm_control_panel.DOMAIN,
        DEFAULT_CONFIG,
    )


async def test_discovery_update_attr(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test update of discovered MQTTAttributes."""
    await help_test_discovery_update_attr(
        hass,
        mqtt_mock_entry_no_yaml_config,
        caplog,
        alarm_control_panel.DOMAIN,
        DEFAULT_CONFIG,
    )


@pytest.mark.parametrize(
    "hass_config",
    [
        {
            mqtt.DOMAIN: {
                alarm_control_panel.DOMAIN: [
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
    ],
)
async def test_unique_id(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test unique id option only creates one alarm per unique_id."""
    await help_test_unique_id(
        hass, mqtt_mock_entry_no_yaml_config, alarm_control_panel.DOMAIN
    )


async def test_discovery_removal_alarm(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test removal of discovered alarm_control_panel."""
    data = json.dumps(DEFAULT_CONFIG[mqtt.DOMAIN][alarm_control_panel.DOMAIN])
    await help_test_discovery_removal(
        hass, mqtt_mock_entry_no_yaml_config, caplog, alarm_control_panel.DOMAIN, data
    )


async def test_discovery_update_alarm_topic_and_template(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test update of discovered alarm_control_panel."""
    config1 = copy.deepcopy(DEFAULT_CONFIG[mqtt.DOMAIN][alarm_control_panel.DOMAIN])
    config2 = copy.deepcopy(DEFAULT_CONFIG[mqtt.DOMAIN][alarm_control_panel.DOMAIN])
    config1["name"] = "Beer"
    config2["name"] = "Milk"
    config1["state_topic"] = "alarm/state1"
    config2["state_topic"] = "alarm/state2"
    config1["value_template"] = "{{ value_json.state1.state }}"
    config2["value_template"] = "{{ value_json.state2.state }}"

    state_data1 = [
        ([("alarm/state1", '{"state1":{"state":"armed_away"}}')], "armed_away", None),
    ]
    state_data2 = [
        ([("alarm/state1", '{"state1":{"state":"triggered"}}')], "armed_away", None),
        ([("alarm/state1", '{"state2":{"state":"triggered"}}')], "armed_away", None),
        ([("alarm/state2", '{"state1":{"state":"triggered"}}')], "armed_away", None),
        ([("alarm/state2", '{"state2":{"state":"triggered"}}')], "triggered", None),
    ]

    await help_test_discovery_update(
        hass,
        mqtt_mock_entry_no_yaml_config,
        caplog,
        alarm_control_panel.DOMAIN,
        config1,
        config2,
        state_data1=state_data1,
        state_data2=state_data2,
    )


async def test_discovery_update_alarm_template(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test update of discovered alarm_control_panel."""
    config1 = copy.deepcopy(DEFAULT_CONFIG[mqtt.DOMAIN][alarm_control_panel.DOMAIN])
    config2 = copy.deepcopy(DEFAULT_CONFIG[mqtt.DOMAIN][alarm_control_panel.DOMAIN])
    config1["name"] = "Beer"
    config2["name"] = "Milk"
    config1["state_topic"] = "alarm/state1"
    config2["state_topic"] = "alarm/state1"
    config1["value_template"] = "{{ value_json.state1.state }}"
    config2["value_template"] = "{{ value_json.state2.state }}"

    state_data1 = [
        ([("alarm/state1", '{"state1":{"state":"armed_away"}}')], "armed_away", None),
    ]
    state_data2 = [
        ([("alarm/state1", '{"state1":{"state":"triggered"}}')], "armed_away", None),
        ([("alarm/state1", '{"state2":{"state":"triggered"}}')], "triggered", None),
    ]

    await help_test_discovery_update(
        hass,
        mqtt_mock_entry_no_yaml_config,
        caplog,
        alarm_control_panel.DOMAIN,
        config1,
        config2,
        state_data1=state_data1,
        state_data2=state_data2,
    )


async def test_discovery_update_unchanged_alarm(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test update of discovered alarm_control_panel."""
    config1 = copy.deepcopy(DEFAULT_CONFIG[mqtt.DOMAIN][alarm_control_panel.DOMAIN])
    config1["name"] = "Beer"

    data1 = json.dumps(config1)
    with patch(
        "homeassistant.components.mqtt.alarm_control_panel.MqttAlarm.discovery_update"
    ) as discovery_update:
        await help_test_discovery_update_unchanged(
            hass,
            mqtt_mock_entry_no_yaml_config,
            caplog,
            alarm_control_panel.DOMAIN,
            data1,
            discovery_update,
        )


@pytest.mark.no_fail_on_log_exception
async def test_discovery_broken(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test handling of bad discovery message."""
    data1 = '{ "name": "Beer" }'
    data2 = (
        '{ "name": "Milk",'
        '  "state_topic": "test_topic",'
        '  "command_topic": "test_topic" }'
    )
    await help_test_discovery_broken(
        hass,
        mqtt_mock_entry_no_yaml_config,
        caplog,
        alarm_control_panel.DOMAIN,
        data1,
        data2,
    )


@pytest.mark.parametrize(
    ("topic", "value"),
    [
        ("state_topic", "armed_home"),
        ("state_topic", "disarmed"),
    ],
)
async def test_encoding_subscribable_topics(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    topic: str,
    value: str,
) -> None:
    """Test handling of incoming encoded payload."""
    await help_test_encoding_subscribable_topics(
        hass,
        mqtt_mock_entry_no_yaml_config,
        alarm_control_panel.DOMAIN,
        DEFAULT_CONFIG[mqtt.DOMAIN][alarm_control_panel.DOMAIN],
        topic,
        value,
    )


async def test_entity_device_info_with_connection(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test MQTT alarm control panel device registry integration."""
    await help_test_entity_device_info_with_connection(
        hass,
        mqtt_mock_entry_no_yaml_config,
        alarm_control_panel.DOMAIN,
        DEFAULT_CONFIG,
    )


async def test_entity_device_info_with_identifier(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test MQTT alarm control panel device registry integration."""
    await help_test_entity_device_info_with_identifier(
        hass,
        mqtt_mock_entry_no_yaml_config,
        alarm_control_panel.DOMAIN,
        DEFAULT_CONFIG,
    )


async def test_entity_device_info_update(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test device registry update."""
    await help_test_entity_device_info_update(
        hass,
        mqtt_mock_entry_no_yaml_config,
        alarm_control_panel.DOMAIN,
        DEFAULT_CONFIG,
    )


async def test_entity_device_info_remove(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test device registry remove."""
    await help_test_entity_device_info_remove(
        hass,
        mqtt_mock_entry_no_yaml_config,
        alarm_control_panel.DOMAIN,
        DEFAULT_CONFIG,
    )


async def test_entity_id_update_subscriptions(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test MQTT subscriptions are managed when entity_id is updated."""
    await help_test_entity_id_update_subscriptions(
        hass, mqtt_mock_entry_no_yaml_config, alarm_control_panel.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_id_update_discovery_update(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test MQTT discovery update when entity_id is updated."""
    await help_test_entity_id_update_discovery_update(
        hass,
        mqtt_mock_entry_no_yaml_config,
        alarm_control_panel.DOMAIN,
        DEFAULT_CONFIG,
    )


async def test_entity_debug_info_message(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test MQTT debug info."""
    await help_test_entity_debug_info_message(
        hass,
        mqtt_mock_entry_no_yaml_config,
        alarm_control_panel.DOMAIN,
        DEFAULT_CONFIG,
        alarm_control_panel.SERVICE_ALARM_DISARM,
        command_payload="DISARM",
    )


@pytest.mark.parametrize(
    ("service", "topic", "parameters", "payload", "template", "tpl_par", "tpl_output"),
    [
        (
            alarm_control_panel.SERVICE_ALARM_ARM_AWAY,
            "command_topic",
            {"code": "secret"},
            "ARM_AWAY",
            "command_template",
            "code",
            b"s",
        ),
        (
            alarm_control_panel.SERVICE_ALARM_DISARM,
            "command_topic",
            {"code": "secret"},
            "DISARM",
            "command_template",
            "code",
            b"s",
        ),
    ],
)
async def test_publishing_with_custom_encoding(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
    caplog: pytest.LogCaptureFixture,
    service: str,
    topic: str,
    parameters: dict[str, Any],
    payload: str,
    template: str | None,
    tpl_par: str,
    tpl_output: PublishPayloadType,
) -> None:
    """Test publishing MQTT payload with different encoding."""
    domain = alarm_control_panel.DOMAIN
    config = DEFAULT_CONFIG

    await help_test_publishing_with_custom_encoding(
        hass,
        mqtt_mock_entry_no_yaml_config,
        caplog,
        domain,
        config,
        service,
        topic,
        parameters,
        payload,
        template,
        tpl_par=tpl_par,
        tpl_output=tpl_output,
    )


async def test_reloadable(
    hass: HomeAssistant,
    mqtt_client_mock: MqttMockPahoClient,
) -> None:
    """Test reloading the MQTT platform."""
    domain = alarm_control_panel.DOMAIN
    config = DEFAULT_CONFIG
    await help_test_reloadable(hass, mqtt_client_mock, domain, config)


@pytest.mark.parametrize("hass_config", [DEFAULT_CONFIG])
async def test_setup_manual_entity_from_yaml(
    hass: HomeAssistant, mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator
) -> None:
    """Test setup manual configured MQTT entity."""
    await mqtt_mock_entry_no_yaml_config()
    platform = alarm_control_panel.DOMAIN
    assert hass.states.get(f"{platform}.test")


async def test_unload_entry(
    hass: HomeAssistant,
    mqtt_mock_entry_no_yaml_config: MqttMockHAClientGenerator,
) -> None:
    """Test unloading the config entry."""
    domain = alarm_control_panel.DOMAIN
    config = DEFAULT_CONFIG
    await help_test_unload_config_entry_with_platform(
        hass, mqtt_mock_entry_no_yaml_config, domain, config
    )
