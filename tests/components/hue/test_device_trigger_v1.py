"""The tests for Philips Hue device triggers for V1 bridge."""
from homeassistant.components import automation, hue
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.components.hue.v1 import device_trigger
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from .conftest import setup_platform
from .test_sensor_v1 import HUE_DIMMER_REMOTE_1, HUE_TAP_REMOTE_1

from tests.common import assert_lists_same, async_get_device_automations

REMOTES_RESPONSE = {"7": HUE_TAP_REMOTE_1, "8": HUE_DIMMER_REMOTE_1}


async def test_get_triggers(hass: HomeAssistant, mock_bridge_v1, device_reg) -> None:
    """Test we get the expected triggers from a hue remote."""
    mock_bridge_v1.mock_sensor_responses.append(REMOTES_RESPONSE)
    await setup_platform(hass, mock_bridge_v1, ["sensor", "binary_sensor"])

    assert len(mock_bridge_v1.mock_requests) == 1
    # 2 remotes, just 1 battery sensor
    assert len(hass.states.async_all()) == 1

    # Get triggers for specific tap switch
    hue_tap_device = device_reg.async_get_device(
        {(hue.DOMAIN, "00:00:00:00:00:44:23:08")}
    )
    triggers = await async_get_device_automations(
        hass, DeviceAutomationType.TRIGGER, hue_tap_device.id
    )

    expected_triggers = [
        {
            "platform": "device",
            "domain": hue.DOMAIN,
            "device_id": hue_tap_device.id,
            "type": t_type,
            "subtype": t_subtype,
            "metadata": {},
        }
        for t_type, t_subtype in device_trigger.HUE_TAP_REMOTE
    ]
    assert_lists_same(triggers, expected_triggers)

    # Get triggers for specific dimmer switch
    hue_dimmer_device = device_reg.async_get_device(
        {(hue.DOMAIN, "00:17:88:01:10:3e:3a:dc")}
    )
    triggers = await async_get_device_automations(
        hass, DeviceAutomationType.TRIGGER, hue_dimmer_device.id
    )

    trigger_batt = {
        "platform": "device",
        "domain": "sensor",
        "device_id": hue_dimmer_device.id,
        "type": "battery_level",
        "entity_id": "sensor.hue_dimmer_switch_1_battery_level",
        "metadata": {"secondary": True},
    }
    expected_triggers = [
        trigger_batt,
        *(
            {
                "platform": "device",
                "domain": hue.DOMAIN,
                "device_id": hue_dimmer_device.id,
                "type": t_type,
                "subtype": t_subtype,
                "metadata": {},
            }
            for t_type, t_subtype in device_trigger.HUE_DIMMER_REMOTE
        ),
    ]
    assert_lists_same(triggers, expected_triggers)


async def test_if_fires_on_state_change(
    hass: HomeAssistant, mock_bridge_v1, device_reg, calls
) -> None:
    """Test for button press trigger firing."""
    mock_bridge_v1.mock_sensor_responses.append(REMOTES_RESPONSE)
    await setup_platform(hass, mock_bridge_v1, ["sensor", "binary_sensor"])
    assert len(mock_bridge_v1.mock_requests) == 1
    assert len(hass.states.async_all()) == 1

    # Set an automation with a specific tap switch trigger
    hue_tap_device = device_reg.async_get_device(
        {(hue.DOMAIN, "00:00:00:00:00:44:23:08")}
    )
    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "trigger": {
                        "platform": "device",
                        "domain": hue.DOMAIN,
                        "device_id": hue_tap_device.id,
                        "type": "remote_button_short_press",
                        "subtype": "button_4",
                    },
                    "action": {
                        "service": "test.automation",
                        "data_template": {
                            "some": "B4 - {{ trigger.event.data.event }}"
                        },
                    },
                },
                {
                    "trigger": {
                        "platform": "device",
                        "domain": hue.DOMAIN,
                        "device_id": "mock-device-id",
                        "type": "remote_button_short_press",
                        "subtype": "button_1",
                    },
                    "action": {
                        "service": "test.automation",
                        "data_template": {
                            "some": "B1 - {{ trigger.event.data.event }}"
                        },
                    },
                },
            ]
        },
    )

    # Fake that the remote is being pressed.
    new_sensor_response = dict(REMOTES_RESPONSE)
    new_sensor_response["7"] = dict(new_sensor_response["7"])
    new_sensor_response["7"]["state"] = {
        "buttonevent": 18,
        "lastupdated": "2019-12-28T22:58:02",
    }
    mock_bridge_v1.mock_sensor_responses.append(new_sensor_response)

    # Force updates to run again
    await mock_bridge_v1.sensor_manager.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(mock_bridge_v1.mock_requests) == 2

    assert len(calls) == 1
    assert calls[0].data["some"] == "B4 - 18"

    # Fake another button press.
    new_sensor_response["7"] = dict(new_sensor_response["7"])
    new_sensor_response["7"]["state"] = {
        "buttonevent": 34,
        "lastupdated": "2019-12-28T22:58:05",
    }
    mock_bridge_v1.mock_sensor_responses.append(new_sensor_response)

    # Force updates to run again
    await mock_bridge_v1.sensor_manager.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert len(mock_bridge_v1.mock_requests) == 3
    assert len(calls) == 1
