"""The tests for the manual_mqtt Alarm Control Panel component."""
from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time

from homeassistant.components import alarm_control_panel
from homeassistant.const import (
    STATE_ALARM_ARMED_AWAY,
    STATE_ALARM_ARMED_HOME,
    STATE_ALARM_ARMED_NIGHT,
    STATE_ALARM_DISARMED,
    STATE_ALARM_PENDING,
    STATE_ALARM_TRIGGERED,
)
from homeassistant.setup import async_setup_component
import homeassistant.util.dt as dt_util

from tests.common import (
    assert_setup_component,
    async_fire_mqtt_message,
    async_fire_time_changed,
)
from tests.components.alarm_control_panel import common

CODE = "HELLO_CODE"


async def test_fail_setup_without_state_topic(hass, mqtt_mock_entry_with_yaml_config):
    """Test for failing with no state topic."""
    with assert_setup_component(0, alarm_control_panel.DOMAIN) as config:
        assert await async_setup_component(
            hass,
            alarm_control_panel.DOMAIN,
            {
                alarm_control_panel.DOMAIN: {
                    "platform": "mqtt_alarm",
                    "command_topic": "alarm/command",
                }
            },
        )
        assert not config[alarm_control_panel.DOMAIN]


async def test_fail_setup_without_command_topic(hass, mqtt_mock_entry_with_yaml_config):
    """Test failing with no command topic."""
    with assert_setup_component(0, alarm_control_panel.DOMAIN):
        assert await async_setup_component(
            hass,
            alarm_control_panel.DOMAIN,
            {
                alarm_control_panel.DOMAIN: {
                    "platform": "mqtt_alarm",
                    "state_topic": "alarm/state",
                }
            },
        )


async def test_arm_home_no_pending(hass, mqtt_mock_entry_with_yaml_config):
    """Test arm home method."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "code": CODE,
                "pending_time": 0,
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_arm_home(hass, CODE)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_HOME


async def test_arm_home_no_pending_when_code_not_req(
    hass, mqtt_mock_entry_with_yaml_config
):
    """Test arm home method."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "code": CODE,
                "code_arm_required": False,
                "pending_time": 0,
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_arm_home(hass, 0)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_HOME


async def test_arm_home_with_pending(hass, mqtt_mock_entry_with_yaml_config):
    """Test arm home method."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "code": CODE,
                "pending_time": 1,
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_arm_home(hass, CODE, entity_id)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_PENDING

    state = hass.states.get(entity_id)
    assert state.attributes["post_pending_state"] == STATE_ALARM_ARMED_HOME

    future = dt_util.utcnow() + timedelta(seconds=1)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_HOME


async def test_arm_home_with_invalid_code(hass, mqtt_mock_entry_with_yaml_config):
    """Attempt to arm home without a valid code."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "code": CODE,
                "pending_time": 1,
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_arm_home(hass, f"{CODE}2")
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED


async def test_arm_away_no_pending(hass, mqtt_mock_entry_with_yaml_config):
    """Test arm home method."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "code": CODE,
                "pending_time": 0,
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_arm_away(hass, CODE, entity_id)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_AWAY


async def test_arm_away_no_pending_when_code_not_req(
    hass, mqtt_mock_entry_with_yaml_config
):
    """Test arm home method."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "code_arm_required": False,
                "code": CODE,
                "pending_time": 0,
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_arm_away(hass, 0, entity_id)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_AWAY


async def test_arm_home_with_template_code(hass, mqtt_mock_entry_with_yaml_config):
    """Attempt to arm with a template-based code."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "code_template": '{{ "abc" }}',
                "pending_time": 0,
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_arm_home(hass, "abc")
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_ALARM_ARMED_HOME


async def test_arm_away_with_pending(hass, mqtt_mock_entry_with_yaml_config):
    """Test arm home method."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "code": CODE,
                "pending_time": 1,
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_arm_away(hass, CODE)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_PENDING

    state = hass.states.get(entity_id)
    assert state.attributes["post_pending_state"] == STATE_ALARM_ARMED_AWAY

    future = dt_util.utcnow() + timedelta(seconds=1)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_AWAY


async def test_arm_away_with_invalid_code(hass, mqtt_mock_entry_with_yaml_config):
    """Attempt to arm away without a valid code."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "code": CODE,
                "pending_time": 1,
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_arm_away(hass, f"{CODE}2")
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED


async def test_arm_night_no_pending(hass, mqtt_mock_entry_with_yaml_config):
    """Test arm night method."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "code": CODE,
                "pending_time": 0,
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_arm_night(hass, CODE, entity_id)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_NIGHT


async def test_arm_night_no_pending_when_code_not_req(
    hass, mqtt_mock_entry_with_yaml_config
):
    """Test arm night method."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "code_arm_required": False,
                "code": CODE,
                "pending_time": 0,
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_arm_night(hass, 0, entity_id)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_NIGHT


async def test_arm_night_with_pending(hass, mqtt_mock_entry_with_yaml_config):
    """Test arm night method."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "code": CODE,
                "pending_time": 1,
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_arm_night(hass, CODE)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_PENDING

    state = hass.states.get(entity_id)
    assert state.attributes["post_pending_state"] == STATE_ALARM_ARMED_NIGHT

    future = dt_util.utcnow() + timedelta(seconds=1)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_NIGHT

    # Do not go to the pending state when updating to the same state
    await common.async_alarm_arm_night(hass, CODE, entity_id)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_NIGHT


async def test_arm_night_with_invalid_code(hass, mqtt_mock_entry_with_yaml_config):
    """Attempt to arm night without a valid code."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "code": CODE,
                "pending_time": 1,
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_arm_night(hass, f"{CODE}2")
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED


async def test_trigger_no_pending(hass, mqtt_mock_entry_with_yaml_config):
    """Test triggering when no pending submitted method."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "trigger_time": 1,
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_trigger(hass, entity_id=entity_id)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_PENDING

    future = dt_util.utcnow() + timedelta(seconds=60)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_TRIGGERED


async def test_trigger_with_delay(hass, mqtt_mock_entry_with_yaml_config):
    """Test trigger method and switch from pending to triggered."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "code": CODE,
                "delay_time": 1,
                "pending_time": 0,
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_arm_away(hass, CODE)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_AWAY

    await common.async_alarm_trigger(hass, entity_id=entity_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_ALARM_PENDING
    assert state.attributes["post_pending_state"] == STATE_ALARM_TRIGGERED

    future = dt_util.utcnow() + timedelta(seconds=1)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_ALARM_TRIGGERED


async def test_trigger_zero_trigger_time(hass, mqtt_mock_entry_with_yaml_config):
    """Test disabled trigger."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "pending_time": 0,
                "trigger_time": 0,
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_trigger(hass)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED


async def test_trigger_zero_trigger_time_with_pending(
    hass, mqtt_mock_entry_with_yaml_config
):
    """Test disabled trigger."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "pending_time": 2,
                "trigger_time": 0,
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_trigger(hass)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED


async def test_trigger_with_pending(hass, mqtt_mock_entry_with_yaml_config):
    """Test arm home method."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "pending_time": 2,
                "trigger_time": 3,
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_trigger(hass)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_PENDING

    state = hass.states.get(entity_id)
    assert state.attributes["post_pending_state"] == STATE_ALARM_TRIGGERED

    future = dt_util.utcnow() + timedelta(seconds=2)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_TRIGGERED

    future = dt_util.utcnow() + timedelta(seconds=5)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED


async def test_trigger_with_disarm_after_trigger(
    hass, mqtt_mock_entry_with_yaml_config
):
    """Test disarm after trigger."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "trigger_time": 5,
                "pending_time": 0,
                "disarm_after_trigger": True,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_trigger(hass, entity_id=entity_id)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_TRIGGERED

    future = dt_util.utcnow() + timedelta(seconds=5)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED


async def test_trigger_with_zero_specific_trigger_time(
    hass, mqtt_mock_entry_with_yaml_config
):
    """Test trigger method."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "trigger_time": 5,
                "disarmed": {"trigger_time": 0},
                "pending_time": 0,
                "disarm_after_trigger": True,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_trigger(hass, entity_id=entity_id)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED


async def test_trigger_with_unused_zero_specific_trigger_time(
    hass, mqtt_mock_entry_with_yaml_config
):
    """Test disarm after trigger."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "trigger_time": 5,
                "armed_home": {"trigger_time": 0},
                "pending_time": 0,
                "disarm_after_trigger": True,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_trigger(hass, entity_id=entity_id)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_TRIGGERED

    future = dt_util.utcnow() + timedelta(seconds=5)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED


async def test_trigger_with_specific_trigger_time(
    hass, mqtt_mock_entry_with_yaml_config
):
    """Test disarm after trigger."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "disarmed": {"trigger_time": 5},
                "pending_time": 0,
                "disarm_after_trigger": True,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_trigger(hass, entity_id=entity_id)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_TRIGGERED

    future = dt_util.utcnow() + timedelta(seconds=5)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED


async def test_back_to_back_trigger_with_no_disarm_after_trigger(
    hass, mqtt_mock_entry_with_yaml_config
):
    """Test no disarm after back to back trigger."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "trigger_time": 5,
                "pending_time": 0,
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_arm_away(hass, CODE, entity_id)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_AWAY

    await common.async_alarm_trigger(hass, entity_id=entity_id)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_TRIGGERED

    future = dt_util.utcnow() + timedelta(seconds=5)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_AWAY

    await common.async_alarm_trigger(hass, entity_id=entity_id)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_TRIGGERED

    future = dt_util.utcnow() + timedelta(seconds=5)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_AWAY


async def test_disarm_while_pending_trigger(hass, mqtt_mock_entry_with_yaml_config):
    """Test disarming while pending state."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "trigger_time": 5,
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_trigger(hass)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_PENDING

    await common.async_alarm_disarm(hass, entity_id=entity_id)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    future = dt_util.utcnow() + timedelta(seconds=5)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED


async def test_disarm_during_trigger_with_invalid_code(
    hass, mqtt_mock_entry_with_yaml_config
):
    """Test disarming while code is invalid."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "pending_time": 5,
                "code": f"{CODE}2",
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_trigger(hass)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_PENDING

    await common.async_alarm_disarm(hass, entity_id=entity_id)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_PENDING

    future = dt_util.utcnow() + timedelta(seconds=5)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_TRIGGERED


async def test_trigger_with_unused_specific_delay(
    hass, mqtt_mock_entry_with_yaml_config
):
    """Test trigger method and switch from pending to triggered."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "code": CODE,
                "delay_time": 5,
                "pending_time": 0,
                "armed_home": {"delay_time": 10},
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_arm_away(hass, CODE)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_AWAY

    await common.async_alarm_trigger(hass, entity_id=entity_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_ALARM_PENDING
    assert state.attributes["post_pending_state"] == STATE_ALARM_TRIGGERED

    future = dt_util.utcnow() + timedelta(seconds=5)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_ALARM_TRIGGERED


async def test_trigger_with_specific_delay(hass, mqtt_mock_entry_with_yaml_config):
    """Test trigger method and switch from pending to triggered."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "code": CODE,
                "delay_time": 10,
                "pending_time": 0,
                "armed_away": {"delay_time": 1},
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_arm_away(hass, CODE)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_AWAY

    await common.async_alarm_trigger(hass, entity_id=entity_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_ALARM_PENDING
    assert state.attributes["post_pending_state"] == STATE_ALARM_TRIGGERED

    future = dt_util.utcnow() + timedelta(seconds=1)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_ALARM_TRIGGERED


async def test_trigger_with_pending_and_delay(hass, mqtt_mock_entry_with_yaml_config):
    """Test trigger method and switch from pending to triggered."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "code": CODE,
                "delay_time": 1,
                "pending_time": 0,
                "triggered": {"pending_time": 1},
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_arm_away(hass, CODE)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_AWAY

    await common.async_alarm_trigger(hass, entity_id=entity_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_ALARM_PENDING
    assert state.attributes["post_pending_state"] == STATE_ALARM_TRIGGERED

    future = dt_util.utcnow() + timedelta(seconds=1)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_ALARM_PENDING
    assert state.attributes["post_pending_state"] == STATE_ALARM_TRIGGERED

    future += timedelta(seconds=1)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_ALARM_TRIGGERED


async def test_trigger_with_pending_and_specific_delay(
    hass, mqtt_mock_entry_with_yaml_config
):
    """Test trigger method and switch from pending to triggered."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "code": CODE,
                "delay_time": 10,
                "pending_time": 0,
                "armed_away": {"delay_time": 1},
                "triggered": {"pending_time": 1},
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_arm_away(hass, CODE)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_AWAY

    await common.async_alarm_trigger(hass, entity_id=entity_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_ALARM_PENDING
    assert state.attributes["post_pending_state"] == STATE_ALARM_TRIGGERED

    future = dt_util.utcnow() + timedelta(seconds=1)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_ALARM_PENDING
    assert state.attributes["post_pending_state"] == STATE_ALARM_TRIGGERED

    future += timedelta(seconds=1)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_ALARM_TRIGGERED


async def test_armed_home_with_specific_pending(hass, mqtt_mock_entry_with_yaml_config):
    """Test arm home method."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "pending_time": 10,
                "armed_home": {"pending_time": 2},
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    await common.async_alarm_arm_home(hass)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_PENDING

    future = dt_util.utcnow() + timedelta(seconds=2)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_HOME


async def test_armed_away_with_specific_pending(hass, mqtt_mock_entry_with_yaml_config):
    """Test arm home method."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "pending_time": 10,
                "armed_away": {"pending_time": 2},
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    await common.async_alarm_arm_away(hass)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_PENDING

    future = dt_util.utcnow() + timedelta(seconds=2)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_AWAY


async def test_armed_night_with_specific_pending(
    hass, mqtt_mock_entry_with_yaml_config
):
    """Test arm home method."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "pending_time": 10,
                "armed_night": {"pending_time": 2},
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    await common.async_alarm_arm_night(hass)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_PENDING

    future = dt_util.utcnow() + timedelta(seconds=2)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_NIGHT


async def test_trigger_with_specific_pending(hass, mqtt_mock_entry_with_yaml_config):
    """Test arm home method."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "pending_time": 10,
                "triggered": {"pending_time": 2},
                "trigger_time": 3,
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    await common.async_alarm_trigger(hass)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_PENDING

    future = dt_util.utcnow() + timedelta(seconds=2)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_TRIGGERED

    future = dt_util.utcnow() + timedelta(seconds=5)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED


async def test_arm_away_after_disabled_disarmed(hass, mqtt_mock_entry_with_yaml_config):
    """Test pending state with and without zero trigger time."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "code": CODE,
                "pending_time": 0,
                "delay_time": 1,
                "armed_away": {"pending_time": 1},
                "disarmed": {"trigger_time": 0},
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_arm_away(hass, CODE)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_ALARM_PENDING
    assert state.attributes["pre_pending_state"] == STATE_ALARM_DISARMED
    assert state.attributes["post_pending_state"] == STATE_ALARM_ARMED_AWAY

    await common.async_alarm_trigger(hass, entity_id=entity_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_ALARM_PENDING
    assert state.attributes["pre_pending_state"] == STATE_ALARM_DISARMED
    assert state.attributes["post_pending_state"] == STATE_ALARM_ARMED_AWAY

    future = dt_util.utcnow() + timedelta(seconds=1)
    with freeze_time(future):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

        state = hass.states.get(entity_id)
        assert state.state == STATE_ALARM_ARMED_AWAY

        await common.async_alarm_trigger(hass, entity_id=entity_id)
        await hass.async_block_till_done()

        state = hass.states.get(entity_id)
        assert state.state == STATE_ALARM_PENDING
        assert state.attributes["pre_pending_state"] == STATE_ALARM_ARMED_AWAY
        assert state.attributes["post_pending_state"] == STATE_ALARM_TRIGGERED

    future += timedelta(seconds=1)
    with freeze_time(future):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_ALARM_TRIGGERED


async def test_disarm_with_template_code(hass, mqtt_mock_entry_with_yaml_config):
    """Attempt to disarm with a valid or invalid template-based code."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            "alarm_control_panel": {
                "platform": "manual_mqtt",
                "name": "test",
                "code_template": '{{ "" if from_state == "disarmed" else "abc" }}',
                "pending_time": 0,
                "disarm_after_trigger": False,
                "command_topic": "alarm/command",
                "state_topic": "alarm/state",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_arm_home(hass, "def")
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_ALARM_ARMED_HOME

    await common.async_alarm_disarm(hass, "def")
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_ALARM_ARMED_HOME

    await common.async_alarm_disarm(hass, "abc")
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_ALARM_DISARMED


async def test_arm_home_via_command_topic(hass, mqtt_mock_entry_with_yaml_config):
    """Test arming home via command topic."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            alarm_control_panel.DOMAIN: {
                "platform": "manual_mqtt",
                "name": "test",
                "pending_time": 1,
                "state_topic": "alarm/state",
                "command_topic": "alarm/command",
                "payload_arm_home": "ARM_HOME",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    # Fire the arm command via MQTT; ensure state changes to pending
    async_fire_mqtt_message(hass, "alarm/command", "ARM_HOME")
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_ALARM_PENDING

    # Fast-forward a little bit
    future = dt_util.utcnow() + timedelta(seconds=1)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_HOME


async def test_arm_away_via_command_topic(hass, mqtt_mock_entry_with_yaml_config):
    """Test arming away via command topic."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            alarm_control_panel.DOMAIN: {
                "platform": "manual_mqtt",
                "name": "test",
                "pending_time": 1,
                "state_topic": "alarm/state",
                "command_topic": "alarm/command",
                "payload_arm_away": "ARM_AWAY",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    # Fire the arm command via MQTT; ensure state changes to pending
    async_fire_mqtt_message(hass, "alarm/command", "ARM_AWAY")
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_ALARM_PENDING

    # Fast-forward a little bit
    future = dt_util.utcnow() + timedelta(seconds=1)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_AWAY


async def test_arm_night_via_command_topic(hass, mqtt_mock_entry_with_yaml_config):
    """Test arming night via command topic."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            alarm_control_panel.DOMAIN: {
                "platform": "manual_mqtt",
                "name": "test",
                "pending_time": 1,
                "state_topic": "alarm/state",
                "command_topic": "alarm/command",
                "payload_arm_night": "ARM_NIGHT",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    # Fire the arm command via MQTT; ensure state changes to pending
    async_fire_mqtt_message(hass, "alarm/command", "ARM_NIGHT")
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_ALARM_PENDING

    # Fast-forward a little bit
    future = dt_util.utcnow() + timedelta(seconds=1)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_ARMED_NIGHT


async def test_disarm_pending_via_command_topic(hass, mqtt_mock_entry_with_yaml_config):
    """Test disarming pending alarm via command topic."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            alarm_control_panel.DOMAIN: {
                "platform": "manual_mqtt",
                "name": "test",
                "pending_time": 1,
                "state_topic": "alarm/state",
                "command_topic": "alarm/command",
                "payload_disarm": "DISARM",
            }
        },
    )
    await hass.async_block_till_done()

    entity_id = "alarm_control_panel.test"

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED

    await common.async_alarm_trigger(hass)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_PENDING

    # Now that we're pending, receive a command to disarm
    async_fire_mqtt_message(hass, "alarm/command", "DISARM")
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ALARM_DISARMED


async def test_state_changes_are_published_to_mqtt(
    hass, mqtt_mock_entry_with_yaml_config
):
    """Test publishing of MQTT messages when state changes."""
    assert await async_setup_component(
        hass,
        alarm_control_panel.DOMAIN,
        {
            alarm_control_panel.DOMAIN: {
                "platform": "manual_mqtt",
                "name": "test",
                "pending_time": 1,
                "trigger_time": 1,
                "state_topic": "alarm/state",
                "command_topic": "alarm/command",
            }
        },
    )
    await hass.async_block_till_done()

    # Component should send disarmed alarm state on startup
    await hass.async_block_till_done()
    mqtt_mock = await mqtt_mock_entry_with_yaml_config()
    mqtt_mock.async_publish.assert_called_once_with(
        "alarm/state", STATE_ALARM_DISARMED, 0, True
    )
    mqtt_mock.async_publish.reset_mock()

    # Arm in home mode
    await common.async_alarm_arm_home(hass)
    await hass.async_block_till_done()
    mqtt_mock.async_publish.assert_called_once_with(
        "alarm/state", STATE_ALARM_PENDING, 0, True
    )
    mqtt_mock.async_publish.reset_mock()
    # Fast-forward a little bit
    future = dt_util.utcnow() + timedelta(seconds=1)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()
    mqtt_mock.async_publish.assert_called_once_with(
        "alarm/state", STATE_ALARM_ARMED_HOME, 0, True
    )
    mqtt_mock.async_publish.reset_mock()

    # Arm in away mode
    await common.async_alarm_arm_away(hass)
    await hass.async_block_till_done()
    mqtt_mock.async_publish.assert_called_once_with(
        "alarm/state", STATE_ALARM_PENDING, 0, True
    )
    mqtt_mock.async_publish.reset_mock()
    # Fast-forward a little bit
    future = dt_util.utcnow() + timedelta(seconds=1)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()
    mqtt_mock.async_publish.assert_called_once_with(
        "alarm/state", STATE_ALARM_ARMED_AWAY, 0, True
    )
    mqtt_mock.async_publish.reset_mock()

    # Arm in night mode
    await common.async_alarm_arm_night(hass)
    await hass.async_block_till_done()
    mqtt_mock.async_publish.assert_called_once_with(
        "alarm/state", STATE_ALARM_PENDING, 0, True
    )
    mqtt_mock.async_publish.reset_mock()
    # Fast-forward a little bit
    future = dt_util.utcnow() + timedelta(seconds=1)
    with patch(
        ("homeassistant.components.manual_mqtt.alarm_control_panel.dt_util.utcnow"),
        return_value=future,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()
    mqtt_mock.async_publish.assert_called_once_with(
        "alarm/state", STATE_ALARM_ARMED_NIGHT, 0, True
    )
    mqtt_mock.async_publish.reset_mock()

    # Disarm
    await common.async_alarm_disarm(hass)
    await hass.async_block_till_done()
    mqtt_mock.async_publish.assert_called_once_with(
        "alarm/state", STATE_ALARM_DISARMED, 0, True
    )
