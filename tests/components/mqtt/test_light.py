"""The tests for the MQTT light platform.

Configuration for RGB Version with brightness:

light:
  platform: mqtt
  name: "Office Light RGB"
  state_topic: "office/rgb1/light/status"
  command_topic: "office/rgb1/light/switch"
  brightness_state_topic: "office/rgb1/brightness/status"
  brightness_command_topic: "office/rgb1/brightness/set"
  rgb_state_topic: "office/rgb1/rgb/status"
  rgb_command_topic: "office/rgb1/rgb/set"
  qos: 0
  payload_on: "on"
  payload_off: "off"

Configuration for XY Version with brightness:

light:
  platform: mqtt
  name: "Office Light XY"
  state_topic: "office/xy1/light/status"
  command_topic: "office/xy1/light/switch"
  brightness_state_topic: "office/xy1/brightness/status"
  brightness_command_topic: "office/xy1/brightness/set"
  xy_state_topic: "office/xy1/xy/status"
  xy_command_topic: "office/xy1/xy/set"
  qos: 0
  payload_on: "on"
  payload_off: "off"

config without RGB:

light:
  platform: mqtt
  name: "Office Light"
  state_topic: "office/rgb1/light/status"
  command_topic: "office/rgb1/light/switch"
  brightness_state_topic: "office/rgb1/brightness/status"
  brightness_command_topic: "office/rgb1/brightness/set"
  qos: 0
  payload_on: "on"
  payload_off: "off"

config without RGB and brightness:

light:
  platform: mqtt
  name: "Office Light"
  state_topic: "office/rgb1/light/status"
  command_topic: "office/rgb1/light/switch"
  qos: 0
  payload_on: "on"
  payload_off: "off"

config for RGB Version with brightness and scale:

light:
  platform: mqtt
  name: "Office Light RGB"
  state_topic: "office/rgb1/light/status"
  command_topic: "office/rgb1/light/switch"
  brightness_state_topic: "office/rgb1/brightness/status"
  brightness_command_topic: "office/rgb1/brightness/set"
  brightness_scale: 99
  rgb_state_topic: "office/rgb1/rgb/status"
  rgb_command_topic: "office/rgb1/rgb/set"
  rgb_scale: 99
  qos: 0
  payload_on: "on"
  payload_off: "off"

config with brightness and color temp

light:
  platform: mqtt
  name: "Office Light Color Temp"
  state_topic: "office/rgb1/light/status"
  command_topic: "office/rgb1/light/switch"
  brightness_state_topic: "office/rgb1/brightness/status"
  brightness_command_topic: "office/rgb1/brightness/set"
  brightness_scale: 99
  color_temp_state_topic: "office/rgb1/color_temp/status"
  color_temp_command_topic: "office/rgb1/color_temp/set"
  qos: 0
  payload_on: "on"
  payload_off: "off"

config with brightness and effect

light:
  platform: mqtt
  name: "Office Light Color Temp"
  state_topic: "office/rgb1/light/status"
  command_topic: "office/rgb1/light/switch"
  brightness_state_topic: "office/rgb1/brightness/status"
  brightness_command_topic: "office/rgb1/brightness/set"
  brightness_scale: 99
  effect_state_topic: "office/rgb1/effect/status"
  effect_command_topic: "office/rgb1/effect/set"
  effect_list:
    - rainbow
    - colorloop
  qos: 0
  payload_on: "on"
  payload_off: "off"

config for RGB Version with white value and scale:

light:
  platform: mqtt
  name: "Office Light RGB"
  state_topic: "office/rgb1/light/status"
  command_topic: "office/rgb1/light/switch"
  white_value_state_topic: "office/rgb1/white_value/status"
  white_value_command_topic: "office/rgb1/white_value/set"
  white_value_scale: 99
  rgb_state_topic: "office/rgb1/rgb/status"
  rgb_command_topic: "office/rgb1/rgb/set"
  rgb_scale: 99
  qos: 0
  payload_on: "on"
  payload_off: "off"

config for RGB Version with RGB command template:

light:
  platform: mqtt
  name: "Office Light RGB"
  state_topic: "office/rgb1/light/status"
  command_topic: "office/rgb1/light/switch"
  rgb_state_topic: "office/rgb1/rgb/status"
  rgb_command_topic: "office/rgb1/rgb/set"
  rgb_command_template: "{{ '#%02x%02x%02x' | format(red, green, blue)}}"
  qos: 0
  payload_on: "on"
  payload_off: "off"

Configuration for HS Version with brightness:

light:
  platform: mqtt
  name: "Office Light HS"
  state_topic: "office/hs1/light/status"
  command_topic: "office/hs1/light/switch"
  brightness_state_topic: "office/hs1/brightness/status"
  brightness_command_topic: "office/hs1/brightness/set"
  hs_state_topic: "office/hs1/hs/status"
  hs_command_topic: "office/hs1/hs/set"
  qos: 0
  payload_on: "on"
  payload_off: "off"

Configuration with brightness command template:

light:
  platform: mqtt
  name: "Office Light"
  state_topic: "office/rgb1/light/status"
  command_topic: "office/rgb1/light/switch"
  brightness_state_topic: "office/rgb1/brightness/status"
  brightness_command_topic: "office/rgb1/brightness/set"
  brightness_command_template: '{ "brightness": "{{ value }}" }'
  qos: 0
  payload_on: "on"
  payload_off: "off"

Configuration with effect command template:

light:
  platform: mqtt
  name: "Office Light Color Temp"
  state_topic: "office/rgb1/light/status"
  command_topic: "office/rgb1/light/switch"
  effect_state_topic: "office/rgb1/effect/status"
  effect_command_topic: "office/rgb1/effect/set"
  effect_command_template: '{ "effect": "{{ value }}" }'
  effect_list:
    - rainbow
    - colorloop
  qos: 0
  payload_on: "on"
  payload_off: "off"

"""
import copy
from unittest.mock import call, patch

import pytest

from homeassistant.components import light
from homeassistant.components.mqtt.light.schema_basic import (
    CONF_BRIGHTNESS_COMMAND_TOPIC,
    CONF_COLOR_TEMP_COMMAND_TOPIC,
    CONF_EFFECT_COMMAND_TOPIC,
    CONF_EFFECT_LIST,
    CONF_HS_COMMAND_TOPIC,
    CONF_RGB_COMMAND_TOPIC,
    CONF_RGBW_COMMAND_TOPIC,
    CONF_RGBWW_COMMAND_TOPIC,
    CONF_WHITE_VALUE_COMMAND_TOPIC,
    CONF_XY_COMMAND_TOPIC,
    MQTT_LIGHT_ATTRIBUTES_BLOCKED,
)
from homeassistant.const import (
    ATTR_ASSUMED_STATE,
    ATTR_SUPPORTED_FEATURES,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
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

from tests.common import assert_setup_component, async_fire_mqtt_message
from tests.components.light import common

DEFAULT_CONFIG = {
    light.DOMAIN: {"platform": "mqtt", "name": "test", "command_topic": "test-topic"}
}


async def test_fail_setup_if_no_command_topic(hass, mqtt_mock):
    """Test if command fails with command topic."""
    assert await async_setup_component(
        hass, light.DOMAIN, {light.DOMAIN: {"platform": "mqtt", "name": "test"}}
    )
    await hass.async_block_till_done()
    assert hass.states.get("light.test") is None


async def test_legacy_rgb_white_light(hass, mqtt_mock):
    """Test legacy RGB + white light flags brightness support."""
    assert await async_setup_component(
        hass,
        light.DOMAIN,
        {
            light.DOMAIN: {
                "platform": "mqtt",
                "name": "test",
                "command_topic": "test_light_rgb/set",
                "rgb_command_topic": "test_light_rgb/rgb/set",
                "white_value_command_topic": "test_light_rgb/white/set",
            }
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    expected_features = (
        light.SUPPORT_COLOR | light.SUPPORT_BRIGHTNESS | light.SUPPORT_WHITE_VALUE
    )
    assert state.attributes.get(ATTR_SUPPORTED_FEATURES) == expected_features
    assert state.attributes.get(light.ATTR_COLOR_MODE) is None
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == ["hs", "rgbw"]


async def test_no_color_brightness_color_temp_hs_white_xy_if_no_topics(hass, mqtt_mock):
    """Test if there is no color and brightness if no topic."""
    assert await async_setup_component(
        hass,
        light.DOMAIN,
        {
            light.DOMAIN: {
                "platform": "mqtt",
                "name": "test",
                "state_topic": "test_light_rgb/status",
                "command_topic": "test_light_rgb/set",
            }
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN
    assert state.attributes.get("rgb_color") is None
    assert state.attributes.get("brightness") is None
    assert state.attributes.get("color_temp") is None
    assert state.attributes.get("hs_color") is None
    assert state.attributes.get("rgb_color") is None
    assert state.attributes.get("rgbw_color") is None
    assert state.attributes.get("rgbww_color") is None
    assert state.attributes.get("white_value") is None
    assert state.attributes.get("xy_color") is None
    assert state.attributes.get(light.ATTR_COLOR_MODE) is None
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == ["onoff"]

    async_fire_mqtt_message(hass, "test_light_rgb/status", "ON")

    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("rgb_color") is None
    assert state.attributes.get("brightness") is None
    assert state.attributes.get("color_temp") is None
    assert state.attributes.get("hs_color") is None
    assert state.attributes.get("rgb_color") is None
    assert state.attributes.get("rgbw_color") is None
    assert state.attributes.get("rgbww_color") is None
    assert state.attributes.get("white_value") is None
    assert state.attributes.get("xy_color") is None
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "onoff"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == ["onoff"]

    async_fire_mqtt_message(hass, "test_light_rgb/status", "OFF")

    state = hass.states.get("light.test")
    assert state.state == STATE_OFF

    async_fire_mqtt_message(hass, "test_light_rgb/status", "None")

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN


async def test_legacy_controlling_state_via_topic(hass, mqtt_mock):
    """Test the controlling of the state via topic for legacy light (white_value)."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "state_topic": "test_light_rgb/status",
            "command_topic": "test_light_rgb/set",
            "brightness_state_topic": "test_light_rgb/brightness/status",
            "brightness_command_topic": "test_light_rgb/brightness/set",
            "rgb_state_topic": "test_light_rgb/rgb/status",
            "rgb_command_topic": "test_light_rgb/rgb/set",
            "color_temp_state_topic": "test_light_rgb/color_temp/status",
            "color_temp_command_topic": "test_light_rgb/color_temp/set",
            "effect_state_topic": "test_light_rgb/effect/status",
            "effect_command_topic": "test_light_rgb/effect/set",
            "hs_state_topic": "test_light_rgb/hs/status",
            "hs_command_topic": "test_light_rgb/hs/set",
            "white_value_state_topic": "test_light_rgb/white_value/status",
            "white_value_command_topic": "test_light_rgb/white_value/set",
            "xy_state_topic": "test_light_rgb/xy/status",
            "xy_command_topic": "test_light_rgb/xy/set",
            "qos": "0",
            "payload_on": 1,
            "payload_off": 0,
        }
    }
    color_modes = ["color_temp", "hs", "rgbw"]

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN
    assert state.attributes.get("rgb_color") is None
    assert state.attributes.get("brightness") is None
    assert state.attributes.get("color_temp") is None
    assert state.attributes.get("effect") is None
    assert state.attributes.get("hs_color") is None
    assert state.attributes.get("rgb_color") is None
    assert state.attributes.get("rgbw_color") is None
    assert state.attributes.get("rgbww_color") is None
    assert state.attributes.get("white_value") is None
    assert state.attributes.get("xy_color") is None
    assert state.attributes.get(light.ATTR_COLOR_MODE) is None
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes
    assert not state.attributes.get(ATTR_ASSUMED_STATE)

    async_fire_mqtt_message(hass, "test_light_rgb/status", "1")

    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("rgb_color") is None
    assert state.attributes.get("brightness") is None
    assert state.attributes.get("color_temp") is None
    assert state.attributes.get("effect") is None
    assert state.attributes.get("hs_color") is None
    assert state.attributes.get("rgb_color") is None
    assert state.attributes.get("rgbw_color") is None
    assert state.attributes.get("rgbww_color") is None
    assert state.attributes.get("white_value") is None
    assert state.attributes.get("xy_color") is None
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "unknown"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/status", "0")

    state = hass.states.get("light.test")
    assert state.state == STATE_OFF

    async_fire_mqtt_message(hass, "test_light_rgb/status", "1")

    async_fire_mqtt_message(hass, "test_light_rgb/brightness/status", "100")

    light_state = hass.states.get("light.test")
    assert light_state.attributes["brightness"] == 100
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "unknown"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/color_temp/status", "300")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("color_temp") is None
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "unknown"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/white_value/status", "100")

    light_state = hass.states.get("light.test")
    assert light_state.attributes["white_value"] == 100
    assert light_state.attributes["color_temp"] == 300
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "color_temp"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/effect/status", "rainbow")
    light_state = hass.states.get("light.test")
    assert light_state.attributes["effect"] == "rainbow"
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "color_temp"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/status", "1")

    async_fire_mqtt_message(hass, "test_light_rgb/rgb/status", "125,125,125")

    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("rgb_color") == (255, 187, 131)
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "color_temp"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/white_value/status", "0")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("rgb_color") == (255, 255, 255)
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "hs"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/hs/status", "200,50")

    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("hs_color") == (200, 50)
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "hs"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/xy/status", "0.675,0.322")

    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("xy_color") == (0.672, 0.324)
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "hs"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes


async def test_controlling_state_via_topic(hass, mqtt_mock):
    """Test the controlling of the state via topic."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "state_topic": "test_light_rgb/status",
            "command_topic": "test_light_rgb/set",
            "brightness_state_topic": "test_light_rgb/brightness/status",
            "brightness_command_topic": "test_light_rgb/brightness/set",
            "rgb_state_topic": "test_light_rgb/rgb/status",
            "rgb_command_topic": "test_light_rgb/rgb/set",
            "rgbw_state_topic": "test_light_rgb/rgbw/status",
            "rgbw_command_topic": "test_light_rgb/rgbw/set",
            "rgbww_state_topic": "test_light_rgb/rgbww/status",
            "rgbww_command_topic": "test_light_rgb/rgbww/set",
            "color_temp_state_topic": "test_light_rgb/color_temp/status",
            "color_temp_command_topic": "test_light_rgb/color_temp/set",
            "effect_state_topic": "test_light_rgb/effect/status",
            "effect_command_topic": "test_light_rgb/effect/set",
            "hs_state_topic": "test_light_rgb/hs/status",
            "hs_command_topic": "test_light_rgb/hs/set",
            "xy_state_topic": "test_light_rgb/xy/status",
            "xy_command_topic": "test_light_rgb/xy/set",
            "qos": "0",
            "payload_on": 1,
            "payload_off": 0,
        }
    }
    color_modes = ["color_temp", "hs", "rgb", "rgbw", "rgbww", "xy"]

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN
    assert state.attributes.get("rgb_color") is None
    assert state.attributes.get("brightness") is None
    assert state.attributes.get("color_temp") is None
    assert state.attributes.get("effect") is None
    assert state.attributes.get("hs_color") is None
    assert state.attributes.get("rgb_color") is None
    assert state.attributes.get("rgbw_color") is None
    assert state.attributes.get("rgbww_color") is None
    assert state.attributes.get("white_value") is None
    assert state.attributes.get("xy_color") is None
    assert state.attributes.get(light.ATTR_COLOR_MODE) is None
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes
    assert not state.attributes.get(ATTR_ASSUMED_STATE)

    async_fire_mqtt_message(hass, "test_light_rgb/status", "1")
    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("rgb_color") is None
    assert state.attributes.get("brightness") is None
    assert state.attributes.get("color_temp") is None
    assert state.attributes.get("effect") is None
    assert state.attributes.get("hs_color") is None
    assert state.attributes.get("rgb_color") is None
    assert state.attributes.get("rgbw_color") is None
    assert state.attributes.get("rgbww_color") is None
    assert state.attributes.get("white_value") is None
    assert state.attributes.get("xy_color") is None
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "unknown"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/status", "0")
    state = hass.states.get("light.test")
    assert state.state == STATE_OFF

    async_fire_mqtt_message(hass, "test_light_rgb/status", "1")
    async_fire_mqtt_message(hass, "test_light_rgb/brightness/status", "100")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("brightness") is None
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "unknown"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/color_temp/status", "300")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("brightness") == 100
    assert light_state.attributes["color_temp"] == 300
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "color_temp"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/effect/status", "rainbow")
    light_state = hass.states.get("light.test")
    assert light_state.attributes["effect"] == "rainbow"
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "color_temp"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/rgb/status", "125,125,125")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("rgb_color") == (125, 125, 125)
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "rgb"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/rgbw/status", "80,40,20,10")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("rgbw_color") == (80, 40, 20, 10)
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "rgbw"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/rgbww/status", "80,40,20,10,8")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("rgbww_color") == (80, 40, 20, 10, 8)
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "rgbww"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/hs/status", "200,50")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("hs_color") == (200, 50)
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "hs"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/xy/status", "0.675,0.322")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("xy_color") == (0.675, 0.322)
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "xy"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes


async def test_legacy_invalid_state_via_topic(hass, mqtt_mock, caplog):
    """Test handling of empty data via topic."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "state_topic": "test_light_rgb/status",
            "command_topic": "test_light_rgb/set",
            "brightness_state_topic": "test_light_rgb/brightness/status",
            "brightness_command_topic": "test_light_rgb/brightness/set",
            "rgb_state_topic": "test_light_rgb/rgb/status",
            "rgb_command_topic": "test_light_rgb/rgb/set",
            "color_temp_state_topic": "test_light_rgb/color_temp/status",
            "color_temp_command_topic": "test_light_rgb/color_temp/set",
            "effect_state_topic": "test_light_rgb/effect/status",
            "effect_command_topic": "test_light_rgb/effect/set",
            "hs_state_topic": "test_light_rgb/hs/status",
            "hs_command_topic": "test_light_rgb/hs/set",
            "white_value_state_topic": "test_light_rgb/white_value/status",
            "white_value_command_topic": "test_light_rgb/white_value/set",
            "xy_state_topic": "test_light_rgb/xy/status",
            "xy_command_topic": "test_light_rgb/xy/set",
            "qos": "0",
            "payload_on": 1,
            "payload_off": 0,
        }
    }

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN
    assert state.attributes.get("rgb_color") is None
    assert state.attributes.get("brightness") is None
    assert state.attributes.get("color_temp") is None
    assert state.attributes.get("effect") is None
    assert state.attributes.get("hs_color") is None
    assert state.attributes.get("white_value") is None
    assert state.attributes.get("xy_color") is None
    assert not state.attributes.get(ATTR_ASSUMED_STATE)

    async_fire_mqtt_message(hass, "test_light_rgb/status", "1")
    async_fire_mqtt_message(hass, "test_light_rgb/rgb/status", "255,255,255")
    async_fire_mqtt_message(hass, "test_light_rgb/brightness/status", "255")
    async_fire_mqtt_message(hass, "test_light_rgb/effect/status", "none")

    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("rgb_color") == (255, 255, 255)
    assert state.attributes.get("brightness") == 255
    assert state.attributes.get("color_temp") is None
    assert state.attributes.get("effect") == "none"
    assert state.attributes.get("hs_color") == (0, 0)
    assert state.attributes.get("white_value") is None
    assert state.attributes.get("xy_color") == (0.323, 0.329)

    async_fire_mqtt_message(hass, "test_light_rgb/status", "")
    assert "Ignoring empty state message" in caplog.text
    light_state = hass.states.get("light.test")
    assert state.state == STATE_ON

    async_fire_mqtt_message(hass, "test_light_rgb/brightness/status", "")
    assert "Ignoring empty brightness message" in caplog.text
    light_state = hass.states.get("light.test")
    assert light_state.attributes["brightness"] == 255

    async_fire_mqtt_message(hass, "test_light_rgb/effect/status", "")
    assert "Ignoring empty effect message" in caplog.text
    light_state = hass.states.get("light.test")
    assert light_state.attributes["effect"] == "none"

    async_fire_mqtt_message(hass, "test_light_rgb/rgb/status", "")
    assert "Ignoring empty rgb message" in caplog.text
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("rgb_color") == (255, 255, 255)

    async_fire_mqtt_message(hass, "test_light_rgb/hs/status", "")
    assert "Ignoring empty hs message" in caplog.text
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("hs_color") == (0, 0)

    async_fire_mqtt_message(hass, "test_light_rgb/hs/status", "bad,bad")
    assert "Failed to parse hs state update" in caplog.text
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("hs_color") == (0, 0)

    async_fire_mqtt_message(hass, "test_light_rgb/xy/status", "")
    assert "Ignoring empty xy-color message" in caplog.text
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("xy_color") == (0.323, 0.329)

    async_fire_mqtt_message(hass, "test_light_rgb/color_temp/status", "153")
    async_fire_mqtt_message(hass, "test_light_rgb/white_value/status", "255")

    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("rgb_color") == (255, 254, 250)
    assert state.attributes.get("brightness") == 255
    assert state.attributes.get("color_temp") == 153
    assert state.attributes.get("effect") == "none"
    assert state.attributes.get("hs_color") == (54.768, 1.6)
    assert state.attributes.get("white_value") == 255
    assert state.attributes.get("xy_color") == (0.326, 0.333)

    async_fire_mqtt_message(hass, "test_light_rgb/color_temp/status", "")
    assert "Ignoring empty color temp message" in caplog.text
    light_state = hass.states.get("light.test")
    assert light_state.attributes["color_temp"] == 153

    async_fire_mqtt_message(hass, "test_light_rgb/white_value/status", "")
    assert "Ignoring empty white value message" in caplog.text
    light_state = hass.states.get("light.test")
    assert light_state.attributes["white_value"] == 255


async def test_invalid_state_via_topic(hass, mqtt_mock, caplog):
    """Test handling of empty data via topic."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "state_topic": "test_light_rgb/status",
            "command_topic": "test_light_rgb/set",
            "brightness_state_topic": "test_light_rgb/brightness/status",
            "brightness_command_topic": "test_light_rgb/brightness/set",
            "color_mode_state_topic": "test_light_rgb/color_mode/status",
            "rgb_state_topic": "test_light_rgb/rgb/status",
            "rgb_command_topic": "test_light_rgb/rgb/set",
            "rgbw_state_topic": "test_light_rgb/rgbw/status",
            "rgbw_command_topic": "test_light_rgb/rgbw/set",
            "rgbww_state_topic": "test_light_rgb/rgbww/status",
            "rgbww_command_topic": "test_light_rgb/rgbww/set",
            "color_temp_state_topic": "test_light_rgb/color_temp/status",
            "color_temp_command_topic": "test_light_rgb/color_temp/set",
            "effect_state_topic": "test_light_rgb/effect/status",
            "effect_command_topic": "test_light_rgb/effect/set",
            "hs_state_topic": "test_light_rgb/hs/status",
            "hs_command_topic": "test_light_rgb/hs/set",
            "xy_state_topic": "test_light_rgb/xy/status",
            "xy_command_topic": "test_light_rgb/xy/set",
            "qos": "0",
            "payload_on": 1,
            "payload_off": 0,
        }
    }

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN
    assert state.attributes.get("rgb_color") is None
    assert state.attributes.get("rgbw_color") is None
    assert state.attributes.get("rgbww_color") is None
    assert state.attributes.get("brightness") is None
    assert state.attributes.get("color_temp") is None
    assert state.attributes.get("effect") is None
    assert state.attributes.get("hs_color") is None
    assert state.attributes.get("xy_color") is None
    assert not state.attributes.get(ATTR_ASSUMED_STATE)

    async_fire_mqtt_message(hass, "test_light_rgb/status", "1")
    async_fire_mqtt_message(hass, "test_light_rgb/color_mode/status", "rgb")
    async_fire_mqtt_message(hass, "test_light_rgb/rgb/status", "255,255,255")
    async_fire_mqtt_message(hass, "test_light_rgb/brightness/status", "255")
    async_fire_mqtt_message(hass, "test_light_rgb/effect/status", "none")

    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("rgb_color") == (255, 255, 255)
    assert state.attributes.get("brightness") == 255
    assert state.attributes.get("color_temp") is None
    assert state.attributes.get("effect") == "none"
    assert state.attributes.get("hs_color") == (0, 0)
    assert state.attributes.get("xy_color") == (0.323, 0.329)
    assert state.attributes.get("color_mode") == "rgb"

    async_fire_mqtt_message(hass, "test_light_rgb/status", "")
    assert "Ignoring empty state message" in caplog.text
    light_state = hass.states.get("light.test")
    assert state.state == STATE_ON

    async_fire_mqtt_message(hass, "test_light_rgb/brightness/status", "")
    assert "Ignoring empty brightness message" in caplog.text
    light_state = hass.states.get("light.test")
    assert light_state.attributes["brightness"] == 255

    async_fire_mqtt_message(hass, "test_light_rgb/color_mode/status", "")
    assert "Ignoring empty color mode message" in caplog.text
    light_state = hass.states.get("light.test")
    assert light_state.attributes["effect"] == "none"

    async_fire_mqtt_message(hass, "test_light_rgb/effect/status", "")
    assert "Ignoring empty effect message" in caplog.text
    light_state = hass.states.get("light.test")
    assert light_state.attributes["effect"] == "none"

    async_fire_mqtt_message(hass, "test_light_rgb/rgb/status", "")
    assert "Ignoring empty rgb message" in caplog.text
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("rgb_color") == (255, 255, 255)

    async_fire_mqtt_message(hass, "test_light_rgb/hs/status", "")
    assert "Ignoring empty hs message" in caplog.text
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("hs_color") == (0, 0)

    async_fire_mqtt_message(hass, "test_light_rgb/hs/status", "bad,bad")
    assert "Failed to parse hs state update" in caplog.text
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("hs_color") == (0, 0)

    async_fire_mqtt_message(hass, "test_light_rgb/xy/status", "")
    assert "Ignoring empty xy-color message" in caplog.text
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("xy_color") == (0.323, 0.329)

    async_fire_mqtt_message(hass, "test_light_rgb/rgbw/status", "255,255,255,1")
    async_fire_mqtt_message(hass, "test_light_rgb/color_mode/status", "rgbw")
    async_fire_mqtt_message(hass, "test_light_rgb/rgbw/status", "")
    assert "Ignoring empty rgbw message" in caplog.text
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("rgbw_color") == (255, 255, 255, 1)

    async_fire_mqtt_message(hass, "test_light_rgb/rgbww/status", "255,255,255,1,2")
    async_fire_mqtt_message(hass, "test_light_rgb/color_mode/status", "rgbww")
    async_fire_mqtt_message(hass, "test_light_rgb/rgbww/status", "")
    assert "Ignoring empty rgbww message" in caplog.text
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("rgbww_color") == (255, 255, 255, 1, 2)

    async_fire_mqtt_message(hass, "test_light_rgb/color_temp/status", "153")
    async_fire_mqtt_message(hass, "test_light_rgb/color_mode/status", "color_temp")

    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("rgb_color") == (255, 254, 250)
    assert state.attributes.get("brightness") == 255
    assert state.attributes.get("color_temp") == 153
    assert state.attributes.get("effect") == "none"
    assert state.attributes.get("hs_color") == (54.768, 1.6)
    assert state.attributes.get("xy_color") == (0.326, 0.333)

    async_fire_mqtt_message(hass, "test_light_rgb/color_temp/status", "")
    assert "Ignoring empty color temp message" in caplog.text
    light_state = hass.states.get("light.test")
    assert light_state.attributes["color_temp"] == 153


async def test_brightness_controlling_scale(hass, mqtt_mock):
    """Test the brightness controlling scale."""
    with assert_setup_component(1, light.DOMAIN):
        assert await async_setup_component(
            hass,
            light.DOMAIN,
            {
                light.DOMAIN: {
                    "platform": "mqtt",
                    "name": "test",
                    "state_topic": "test_scale/status",
                    "command_topic": "test_scale/set",
                    "brightness_state_topic": "test_scale/brightness/status",
                    "brightness_command_topic": "test_scale/brightness/set",
                    "brightness_scale": "99",
                    "qos": 0,
                    "payload_on": "on",
                    "payload_off": "off",
                }
            },
        )
        await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN
    assert state.attributes.get("brightness") is None
    assert not state.attributes.get(ATTR_ASSUMED_STATE)

    async_fire_mqtt_message(hass, "test_scale/status", "on")

    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("brightness") is None

    async_fire_mqtt_message(hass, "test_scale/status", "off")

    state = hass.states.get("light.test")
    assert state.state == STATE_OFF

    async_fire_mqtt_message(hass, "test_scale/status", "on")

    async_fire_mqtt_message(hass, "test_scale/brightness/status", "99")

    light_state = hass.states.get("light.test")
    assert light_state.attributes["brightness"] == 255


async def test_brightness_from_rgb_controlling_scale(hass, mqtt_mock):
    """Test the brightness controlling scale."""
    with assert_setup_component(1, light.DOMAIN):
        assert await async_setup_component(
            hass,
            light.DOMAIN,
            {
                light.DOMAIN: {
                    "platform": "mqtt",
                    "name": "test",
                    "state_topic": "test_scale_rgb/status",
                    "command_topic": "test_scale_rgb/set",
                    "rgb_state_topic": "test_scale_rgb/rgb/status",
                    "rgb_command_topic": "test_scale_rgb/rgb/set",
                    "qos": 0,
                    "payload_on": "on",
                    "payload_off": "off",
                }
            },
        )
        await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN
    assert state.attributes.get("brightness") is None
    assert not state.attributes.get(ATTR_ASSUMED_STATE)

    async_fire_mqtt_message(hass, "test_scale_rgb/status", "on")
    async_fire_mqtt_message(hass, "test_scale_rgb/rgb/status", "255,0,0")

    state = hass.states.get("light.test")
    assert state.attributes.get("brightness") == 255

    async_fire_mqtt_message(hass, "test_scale_rgb/rgb/status", "127,0,0")

    state = hass.states.get("light.test")
    assert state.attributes.get("brightness") == 127


async def test_legacy_white_value_controlling_scale(hass, mqtt_mock):
    """Test the white_value controlling scale."""
    with assert_setup_component(1, light.DOMAIN):
        assert await async_setup_component(
            hass,
            light.DOMAIN,
            {
                light.DOMAIN: {
                    "platform": "mqtt",
                    "name": "test",
                    "state_topic": "test_scale/status",
                    "command_topic": "test_scale/set",
                    "white_value_state_topic": "test_scale/white_value/status",
                    "white_value_command_topic": "test_scale/white_value/set",
                    "white_value_scale": "99",
                    "qos": 0,
                    "payload_on": "on",
                    "payload_off": "off",
                }
            },
        )
        await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN
    assert state.attributes.get("white_value") is None
    assert not state.attributes.get(ATTR_ASSUMED_STATE)

    async_fire_mqtt_message(hass, "test_scale/status", "on")

    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("white_value") is None

    async_fire_mqtt_message(hass, "test_scale/status", "off")

    state = hass.states.get("light.test")
    assert state.state == STATE_OFF

    async_fire_mqtt_message(hass, "test_scale/status", "on")

    async_fire_mqtt_message(hass, "test_scale/white_value/status", "99")

    light_state = hass.states.get("light.test")
    assert light_state.attributes["white_value"] == 255


async def test_legacy_controlling_state_via_topic_with_templates(hass, mqtt_mock):
    """Test the setting of the state with a template."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "state_topic": "test_light_rgb/status",
            "command_topic": "test_light_rgb/set",
            "brightness_command_topic": "test_light_rgb/brightness/set",
            "rgb_command_topic": "test_light_rgb/rgb/set",
            "color_temp_command_topic": "test_light_rgb/color_temp/set",
            "effect_command_topic": "test_light_rgb/effect/set",
            "hs_command_topic": "test_light_rgb/hs/set",
            "white_value_command_topic": "test_light_rgb/white_value/set",
            "xy_command_topic": "test_light_rgb/xy/set",
            "brightness_state_topic": "test_light_rgb/brightness/status",
            "color_temp_state_topic": "test_light_rgb/color_temp/status",
            "effect_state_topic": "test_light_rgb/effect/status",
            "hs_state_topic": "test_light_rgb/hs/status",
            "rgb_state_topic": "test_light_rgb/rgb/status",
            "white_value_state_topic": "test_light_rgb/white_value/status",
            "xy_state_topic": "test_light_rgb/xy/status",
            "state_value_template": "{{ value_json.hello }}",
            "brightness_value_template": "{{ value_json.hello }}",
            "color_temp_value_template": "{{ value_json.hello }}",
            "effect_value_template": "{{ value_json.hello }}",
            "hs_value_template": '{{ value_json.hello | join(",") }}',
            "rgb_value_template": '{{ value_json.hello | join(",") }}',
            "white_value_template": "{{ value_json.hello }}",
            "xy_value_template": '{{ value_json.hello | join(",") }}',
        }
    }

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN
    assert state.attributes.get("brightness") is None
    assert state.attributes.get("rgb_color") is None

    async_fire_mqtt_message(hass, "test_light_rgb/rgb/status", '{"hello": [1, 2, 3]}')
    async_fire_mqtt_message(hass, "test_light_rgb/status", '{"hello": "ON"}')
    async_fire_mqtt_message(hass, "test_light_rgb/brightness/status", '{"hello": "50"}')
    async_fire_mqtt_message(
        hass, "test_light_rgb/color_temp/status", '{"hello": "300"}'
    )
    async_fire_mqtt_message(
        hass, "test_light_rgb/effect/status", '{"hello": "rainbow"}'
    )

    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("brightness") == 50
    assert state.attributes.get("rgb_color") == (84, 169, 255)
    assert state.attributes.get("color_temp") is None
    assert state.attributes.get("effect") == "rainbow"
    assert state.attributes.get("white_value") is None

    async_fire_mqtt_message(
        hass, "test_light_rgb/white_value/status", '{"hello": "75"}'
    )

    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("brightness") == 50
    assert state.attributes.get("rgb_color") == (255, 187, 131)
    assert state.attributes.get("color_temp") == 300
    assert state.attributes.get("effect") == "rainbow"
    assert state.attributes.get("white_value") == 75

    async_fire_mqtt_message(hass, "test_light_rgb/hs/status", '{"hello": [100,50]}')
    async_fire_mqtt_message(hass, "test_light_rgb/white_value/status", '{"hello": "0"}')

    state = hass.states.get("light.test")
    assert state.attributes.get("hs_color") == (100, 50)

    async_fire_mqtt_message(
        hass, "test_light_rgb/xy/status", '{"hello": [0.123,0.123]}'
    )

    state = hass.states.get("light.test")
    assert state.attributes.get("xy_color") == (0.14, 0.131)

    async_fire_mqtt_message(hass, "test_light_rgb/status", '{"hello": null}')
    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN


async def test_controlling_state_via_topic_with_templates(hass, mqtt_mock):
    """Test the setting of the state with a template."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "state_topic": "test_light_rgb/status",
            "command_topic": "test_light_rgb/set",
            "brightness_command_topic": "test_light_rgb/brightness/set",
            "rgb_command_topic": "test_light_rgb/rgb/set",
            "rgbw_command_topic": "test_light_rgb/rgbw/set",
            "rgbww_command_topic": "test_light_rgb/rgbw/set",
            "color_temp_command_topic": "test_light_rgb/color_temp/set",
            "effect_command_topic": "test_light_rgb/effect/set",
            "hs_command_topic": "test_light_rgb/hs/set",
            "xy_command_topic": "test_light_rgb/xy/set",
            "brightness_state_topic": "test_light_rgb/brightness/status",
            "color_temp_state_topic": "test_light_rgb/color_temp/status",
            "effect_state_topic": "test_light_rgb/effect/status",
            "hs_state_topic": "test_light_rgb/hs/status",
            "rgb_state_topic": "test_light_rgb/rgb/status",
            "rgbw_state_topic": "test_light_rgb/rgbw/status",
            "rgbww_state_topic": "test_light_rgb/rgbww/status",
            "xy_state_topic": "test_light_rgb/xy/status",
            "state_value_template": "{{ value_json.hello }}",
            "brightness_value_template": "{{ value_json.hello }}",
            "color_temp_value_template": "{{ value_json.hello }}",
            "effect_value_template": "{{ value_json.hello }}",
            "hs_value_template": '{{ value_json.hello | join(",") }}',
            "rgb_value_template": '{{ value_json.hello | join(",") }}',
            "rgbw_value_template": '{{ value_json.hello | join(",") }}',
            "rgbww_value_template": '{{ value_json.hello | join(",") }}',
            "xy_value_template": '{{ value_json.hello | join(",") }}',
        }
    }
    color_modes = ["color_temp", "hs", "rgb", "rgbw", "rgbww", "xy"]

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN
    assert state.attributes.get("brightness") is None
    assert state.attributes.get("rgb_color") is None

    async_fire_mqtt_message(hass, "test_light_rgb/rgb/status", '{"hello": [1, 2, 3]}')
    async_fire_mqtt_message(hass, "test_light_rgb/status", '{"hello": "ON"}')
    async_fire_mqtt_message(hass, "test_light_rgb/brightness/status", '{"hello": "50"}')
    async_fire_mqtt_message(
        hass, "test_light_rgb/effect/status", '{"hello": "rainbow"}'
    )
    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("brightness") == 50
    assert state.attributes.get("rgb_color") == (1, 2, 3)
    assert state.attributes.get("effect") == "rainbow"
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "rgb"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(
        hass, "test_light_rgb/rgbw/status", '{"hello": [1, 2, 3, 4]}'
    )
    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("rgbw_color") == (1, 2, 3, 4)
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "rgbw"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(
        hass, "test_light_rgb/rgbww/status", '{"hello": [1, 2, 3, 4, 5]}'
    )
    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("rgbww_color") == (1, 2, 3, 4, 5)
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "rgbww"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(
        hass, "test_light_rgb/color_temp/status", '{"hello": "300"}'
    )
    state = hass.states.get("light.test")
    assert state.attributes.get("color_temp") == 300
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "color_temp"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/hs/status", '{"hello": [100,50]}')
    state = hass.states.get("light.test")
    assert state.attributes.get("hs_color") == (100, 50)
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "hs"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(
        hass, "test_light_rgb/xy/status", '{"hello": [0.123,0.123]}'
    )
    state = hass.states.get("light.test")
    assert state.attributes.get("xy_color") == (0.123, 0.123)
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "xy"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes


async def test_legacy_sending_mqtt_commands_and_optimistic(hass, mqtt_mock):
    """Test the sending of command in optimistic mode."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "command_topic": "test_light_rgb/set",
            "brightness_command_topic": "test_light_rgb/brightness/set",
            "rgb_command_topic": "test_light_rgb/rgb/set",
            "color_temp_command_topic": "test_light_rgb/color_temp/set",
            "effect_command_topic": "test_light_rgb/effect/set",
            "hs_command_topic": "test_light_rgb/hs/set",
            "white_value_command_topic": "test_light_rgb/white_value/set",
            "xy_command_topic": "test_light_rgb/xy/set",
            "effect_list": ["colorloop", "random"],
            "qos": 2,
            "payload_on": "on",
            "payload_off": "off",
        }
    }
    color_modes = ["color_temp", "hs", "rgbw"]
    fake_state = ha.State(
        "light.test",
        "on",
        {
            "brightness": 95,
            "hs_color": [100, 100],
            "effect": "random",
            "color_temp": 100,
            # TODO: Test restoring state with white_value
            "white_value": 0,
        },
    )
    with patch(
        "homeassistant.helpers.restore_state.RestoreEntity.async_get_last_state",
        return_value=fake_state,
    ), assert_setup_component(1, light.DOMAIN):
        assert await async_setup_component(hass, light.DOMAIN, config)
        await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("brightness") == 95
    assert state.attributes.get("hs_color") == (100, 100)
    assert state.attributes.get("effect") == "random"
    assert state.attributes.get("color_temp") is None
    assert state.attributes.get("white_value") is None
    assert state.attributes.get(ATTR_ASSUMED_STATE)
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "hs"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    await common.async_turn_on(hass, "light.test")
    mqtt_mock.async_publish.assert_called_once_with(
        "test_light_rgb/set", "on", 2, False
    )
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "hs"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    await common.async_turn_off(hass, "light.test")
    mqtt_mock.async_publish.assert_called_once_with(
        "test_light_rgb/set", "off", 2, False
    )
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("light.test")
    assert state.state == STATE_OFF

    mqtt_mock.reset_mock()
    await common.async_turn_on(
        hass, "light.test", brightness=50, xy_color=[0.123, 0.123]
    )
    state = hass.states.get("light.test")
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "hs"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    await common.async_turn_on(hass, "light.test", brightness=50, hs_color=[359, 78])
    state = hass.states.get("light.test")
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "hs"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    await common.async_turn_on(hass, "light.test", rgb_color=[255, 128, 0])
    state = hass.states.get("light.test")
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "hs"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light_rgb/set", "on", 2, False),
            call("test_light_rgb/rgb/set", "255,128,0", 2, False),
            call("test_light_rgb/brightness/set", "50", 2, False),
            call("test_light_rgb/hs/set", "359.0,78.0", 2, False),
            call("test_light_rgb/xy/set", "0.14,0.131", 2, False),
        ],
        any_order=True,
    )

    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes["rgb_color"] == (255, 128, 0)
    assert state.attributes["brightness"] == 50
    assert state.attributes["hs_color"] == (30.118, 100)
    assert state.attributes.get("white_value") is None
    assert state.attributes["xy_color"] == (0.611, 0.375)
    assert state.attributes.get("color_temp") is None

    await common.async_turn_on(hass, "light.test", white_value=80, color_temp=125)
    state = hass.states.get("light.test")
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "color_temp"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light_rgb/white_value/set", "80", 2, False),
            call("test_light_rgb/color_temp/set", "125", 2, False),
        ],
        any_order=True,
    )

    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("rgb_color") == (221, 229, 255)
    assert state.attributes["brightness"] == 50
    assert state.attributes.get("hs_color") == (224.772, 13.249)
    assert state.attributes["white_value"] == 80
    assert state.attributes.get("xy_color") == (0.296, 0.301)
    assert state.attributes["color_temp"] == 125


async def test_sending_mqtt_commands_and_optimistic(hass, mqtt_mock):
    """Test the sending of command in optimistic mode."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "command_topic": "test_light_rgb/set",
            "brightness_command_topic": "test_light_rgb/brightness/set",
            "rgb_command_topic": "test_light_rgb/rgb/set",
            "rgbw_command_topic": "test_light_rgb/rgbw/set",
            "rgbww_command_topic": "test_light_rgb/rgbww/set",
            "color_temp_command_topic": "test_light_rgb/color_temp/set",
            "effect_command_topic": "test_light_rgb/effect/set",
            "hs_command_topic": "test_light_rgb/hs/set",
            "xy_command_topic": "test_light_rgb/xy/set",
            "effect_list": ["colorloop", "random"],
            "qos": 2,
            "payload_on": "on",
            "payload_off": "off",
        }
    }
    color_modes = ["color_temp", "hs", "rgb", "rgbw", "rgbww", "xy"]
    fake_state = ha.State(
        "light.test",
        "on",
        {
            "brightness": 95,
            "hs_color": [100, 100],
            "effect": "random",
            "color_temp": 100,
            "color_mode": "hs",
        },
    )
    with patch(
        "homeassistant.helpers.restore_state.RestoreEntity.async_get_last_state",
        return_value=fake_state,
    ), assert_setup_component(1, light.DOMAIN):
        assert await async_setup_component(hass, light.DOMAIN, config)
        await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("brightness") == 95
    assert state.attributes.get("hs_color") == (100, 100)
    assert state.attributes.get("effect") == "random"
    assert state.attributes.get("color_temp") is None
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "hs"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes
    assert state.attributes.get(ATTR_ASSUMED_STATE)

    await common.async_turn_on(hass, "light.test", effect="colorloop")
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light_rgb/set", "on", 2, False),
            call("test_light_rgb/effect/set", "colorloop", 2, False),
        ],
        any_order=True,
    )
    assert mqtt_mock.async_publish.call_count == 2
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("effect") == "colorloop"
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "hs"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    await common.async_turn_off(hass, "light.test")
    mqtt_mock.async_publish.assert_called_once_with(
        "test_light_rgb/set", "off", 2, False
    )
    mqtt_mock.async_publish.reset_mock()
    state = hass.states.get("light.test")
    assert state.state == STATE_OFF
    assert state.attributes.get(light.ATTR_COLOR_MODE) is None
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    await common.async_turn_on(
        hass, "light.test", brightness=10, rgb_color=[80, 40, 20]
    )
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light_rgb/set", "on", 2, False),
            call("test_light_rgb/brightness/set", "10", 2, False),
            call("test_light_rgb/rgb/set", "80,40,20", 2, False),
        ],
        any_order=True,
    )
    assert mqtt_mock.async_publish.call_count == 3
    mqtt_mock.reset_mock()
    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("brightness") == 10
    assert state.attributes.get("rgb_color") == (80, 40, 20)
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "rgb"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    await common.async_turn_on(
        hass, "light.test", brightness=20, rgbw_color=[80, 40, 20, 10]
    )
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light_rgb/set", "on", 2, False),
            call("test_light_rgb/brightness/set", "20", 2, False),
            call("test_light_rgb/rgbw/set", "80,40,20,10", 2, False),
        ],
        any_order=True,
    )
    assert mqtt_mock.async_publish.call_count == 3
    mqtt_mock.reset_mock()
    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("brightness") == 20
    assert state.attributes.get("rgbw_color") == (80, 40, 20, 10)
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "rgbw"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    await common.async_turn_on(
        hass, "light.test", brightness=40, rgbww_color=[80, 40, 20, 10, 8]
    )
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light_rgb/set", "on", 2, False),
            call("test_light_rgb/brightness/set", "40", 2, False),
            call("test_light_rgb/rgbww/set", "80,40,20,10,8", 2, False),
        ],
        any_order=True,
    )
    assert mqtt_mock.async_publish.call_count == 3
    mqtt_mock.reset_mock()
    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("brightness") == 40
    assert state.attributes.get("rgbww_color") == (80, 40, 20, 10, 8)
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "rgbww"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    await common.async_turn_on(hass, "light.test", brightness=50, hs_color=[359, 78])
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light_rgb/set", "on", 2, False),
            call("test_light_rgb/brightness/set", "50", 2, False),
            call("test_light_rgb/hs/set", "359.0,78.0", 2, False),
        ],
        any_order=True,
    )
    assert mqtt_mock.async_publish.call_count == 3
    mqtt_mock.reset_mock()
    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("brightness") == 50
    assert state.attributes.get("hs_color") == (359.0, 78.0)
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "hs"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    await common.async_turn_on(hass, "light.test", brightness=60, xy_color=[0.2, 0.3])
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light_rgb/set", "on", 2, False),
            call("test_light_rgb/brightness/set", "60", 2, False),
            call("test_light_rgb/xy/set", "0.2,0.3", 2, False),
        ],
        any_order=True,
    )
    assert mqtt_mock.async_publish.call_count == 3
    mqtt_mock.reset_mock()
    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("brightness") == 60
    assert state.attributes.get("xy_color") == (0.2, 0.3)
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "xy"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    await common.async_turn_on(hass, "light.test", color_temp=125)
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light_rgb/color_temp/set", "125", 2, False),
        ],
        any_order=True,
    )
    assert mqtt_mock.async_publish.call_count == 2
    mqtt_mock.reset_mock()
    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("brightness") == 60
    assert state.attributes.get("color_temp") == 125
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "color_temp"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes


async def test_sending_mqtt_rgb_command_with_template(hass, mqtt_mock):
    """Test the sending of RGB command with template."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "command_topic": "test_light_rgb/set",
            "rgb_command_topic": "test_light_rgb/rgb/set",
            "rgb_command_template": '{{ "#%02x%02x%02x" | '
            "format(red, green, blue)}}",
            "payload_on": "on",
            "payload_off": "off",
            "qos": 0,
        }
    }

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN

    await common.async_turn_on(hass, "light.test", rgb_color=[255, 128, 64])

    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light_rgb/set", "on", 0, False),
            call("test_light_rgb/rgb/set", "#ff8040", 0, False),
        ],
        any_order=True,
    )

    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes["rgb_color"] == (255, 128, 64)


async def test_sending_mqtt_rgbw_command_with_template(hass, mqtt_mock):
    """Test the sending of RGBW command with template."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "command_topic": "test_light_rgb/set",
            "rgbw_command_topic": "test_light_rgb/rgbw/set",
            "rgbw_command_template": '{{ "#%02x%02x%02x%02x" | '
            "format(red, green, blue, white)}}",
            "payload_on": "on",
            "payload_off": "off",
            "qos": 0,
        }
    }

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN

    await common.async_turn_on(hass, "light.test", rgbw_color=[255, 128, 64, 32])

    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light_rgb/set", "on", 0, False),
            call("test_light_rgb/rgbw/set", "#ff804020", 0, False),
        ],
        any_order=True,
    )

    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes["rgbw_color"] == (255, 128, 64, 32)


async def test_sending_mqtt_rgbww_command_with_template(hass, mqtt_mock):
    """Test the sending of RGBWW command with template."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "command_topic": "test_light_rgb/set",
            "rgbww_command_topic": "test_light_rgb/rgbww/set",
            "rgbww_command_template": '{{ "#%02x%02x%02x%02x%02x" | '
            "format(red, green, blue, cold_white, warm_white)}}",
            "payload_on": "on",
            "payload_off": "off",
            "qos": 0,
        }
    }

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN

    await common.async_turn_on(hass, "light.test", rgbww_color=[255, 128, 64, 32, 16])

    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light_rgb/set", "on", 0, False),
            call("test_light_rgb/rgbww/set", "#ff80402010", 0, False),
        ],
        any_order=True,
    )

    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes["rgbww_color"] == (255, 128, 64, 32, 16)


async def test_sending_mqtt_color_temp_command_with_template(hass, mqtt_mock):
    """Test the sending of Color Temp command with template."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "command_topic": "test_light_color_temp/set",
            "color_temp_command_topic": "test_light_color_temp/color_temp/set",
            "color_temp_command_template": "{{ (1000 / value) | round(0) }}",
            "payload_on": "on",
            "payload_off": "off",
            "qos": 0,
        }
    }

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN

    await common.async_turn_on(hass, "light.test", color_temp=100)

    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light_color_temp/set", "on", 0, False),
            call("test_light_color_temp/color_temp/set", "10", 0, False),
        ],
        any_order=True,
    )

    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes["color_temp"] == 100


async def test_on_command_first(hass, mqtt_mock):
    """Test on command being sent before brightness."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "command_topic": "test_light/set",
            "brightness_command_topic": "test_light/bright",
            "on_command_type": "first",
        }
    }

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN

    await common.async_turn_on(hass, "light.test", brightness=50)

    # Should get the following MQTT messages.
    #    test_light/set: 'ON'
    #    test_light/bright: 50
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/set", "ON", 0, False),
            call("test_light/bright", "50", 0, False),
        ],
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_off(hass, "light.test")

    mqtt_mock.async_publish.assert_called_once_with("test_light/set", "OFF", 0, False)


async def test_on_command_last(hass, mqtt_mock):
    """Test on command being sent after brightness."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "command_topic": "test_light/set",
            "brightness_command_topic": "test_light/bright",
        }
    }

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN

    await common.async_turn_on(hass, "light.test", brightness=50)

    # Should get the following MQTT messages.
    #    test_light/bright: 50
    #    test_light/set: 'ON'
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/bright", "50", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_off(hass, "light.test")

    mqtt_mock.async_publish.assert_called_once_with("test_light/set", "OFF", 0, False)


async def test_on_command_brightness(hass, mqtt_mock):
    """Test on command being sent as only brightness."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "command_topic": "test_light/set",
            "brightness_command_topic": "test_light/bright",
            "rgb_command_topic": "test_light/rgb",
            "on_command_type": "brightness",
        }
    }

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN

    # Turn on w/ no brightness - should set to max
    await common.async_turn_on(hass, "light.test")

    # Should get the following MQTT messages.
    #    test_light/bright: 255
    mqtt_mock.async_publish.assert_called_once_with(
        "test_light/bright", "255", 0, False
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_off(hass, "light.test")

    mqtt_mock.async_publish.assert_called_once_with("test_light/set", "OFF", 0, False)
    mqtt_mock.async_publish.reset_mock()

    # Turn on w/ brightness
    await common.async_turn_on(hass, "light.test", brightness=50)

    mqtt_mock.async_publish.assert_called_once_with("test_light/bright", "50", 0, False)
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_off(hass, "light.test")

    # Turn on w/ just a color to ensure brightness gets
    # added and sent.
    await common.async_turn_on(hass, "light.test", rgb_color=[255, 128, 0])

    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgb", "255,128,0", 0, False),
            call("test_light/bright", "50", 0, False),
        ],
        any_order=True,
    )


async def test_on_command_brightness_scaled(hass, mqtt_mock):
    """Test brightness scale."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "command_topic": "test_light/set",
            "brightness_command_topic": "test_light/bright",
            "brightness_scale": 100,
            "rgb_command_topic": "test_light/rgb",
            "on_command_type": "brightness",
        }
    }

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN

    # Turn on w/ no brightness - should set to max
    await common.async_turn_on(hass, "light.test")

    # Should get the following MQTT messages.
    #    test_light/bright: 100
    mqtt_mock.async_publish.assert_called_once_with(
        "test_light/bright", "100", 0, False
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_off(hass, "light.test")

    mqtt_mock.async_publish.assert_called_once_with("test_light/set", "OFF", 0, False)
    mqtt_mock.async_publish.reset_mock()

    # Turn on w/ brightness
    await common.async_turn_on(hass, "light.test", brightness=50)

    mqtt_mock.async_publish.assert_called_once_with("test_light/bright", "20", 0, False)
    mqtt_mock.async_publish.reset_mock()

    # Turn on w/ max brightness
    await common.async_turn_on(hass, "light.test", brightness=255)

    mqtt_mock.async_publish.assert_called_once_with(
        "test_light/bright", "100", 0, False
    )
    mqtt_mock.async_publish.reset_mock()

    # Turn on w/ min brightness
    await common.async_turn_on(hass, "light.test", brightness=1)

    mqtt_mock.async_publish.assert_called_once_with("test_light/bright", "1", 0, False)
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_off(hass, "light.test")

    # Turn on w/ just a color to ensure brightness gets
    # added and sent.
    await common.async_turn_on(hass, "light.test", rgb_color=[255, 128, 0])

    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgb", "255,128,0", 0, False),
            call("test_light/bright", "1", 0, False),
        ],
        any_order=True,
    )


async def test_legacy_on_command_rgb(hass, mqtt_mock):
    """Test on command in RGB brightness mode."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "command_topic": "test_light/set",
            "rgb_command_topic": "test_light/rgb",
            "white_value_command_topic": "test_light/white_value",
        }
    }

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN

    await common.async_turn_on(hass, "light.test", brightness=127)

    # Should get the following MQTT messages.
    #    test_light/rgb: '127,127,127'
    #    test_light/set: 'ON'
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgb", "127,127,127", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_on(hass, "light.test", brightness=255)

    # Should get the following MQTT messages.
    #    test_light/rgb: '255,255,255'
    #    test_light/set: 'ON'
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgb", "255,255,255", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_on(hass, "light.test", brightness=1)

    # Should get the following MQTT messages.
    #    test_light/rgb: '1,1,1'
    #    test_light/set: 'ON'
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgb", "1,1,1", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_off(hass, "light.test")

    mqtt_mock.async_publish.assert_called_once_with("test_light/set", "OFF", 0, False)

    # Ensure color gets scaled with brightness.
    await common.async_turn_on(hass, "light.test", rgb_color=[255, 128, 0])

    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgb", "1,0,0", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_on(hass, "light.test", brightness=255)

    # Should get the following MQTT messages.
    #    test_light/rgb: '255,128,0'
    #    test_light/set: 'ON'
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgb", "255,128,0", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()


async def test_on_command_rgb(hass, mqtt_mock):
    """Test on command in RGB brightness mode."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "command_topic": "test_light/set",
            "rgb_command_topic": "test_light/rgb",
        }
    }

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN

    await common.async_turn_on(hass, "light.test", brightness=127)

    # Should get the following MQTT messages.
    #    test_light/rgb: '127,127,127'
    #    test_light/set: 'ON'
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgb", "127,127,127", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_on(hass, "light.test", brightness=255)

    # Should get the following MQTT messages.
    #    test_light/rgb: '255,255,255'
    #    test_light/set: 'ON'
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgb", "255,255,255", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_on(hass, "light.test", brightness=1)

    # Should get the following MQTT messages.
    #    test_light/rgb: '1,1,1'
    #    test_light/set: 'ON'
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgb", "1,1,1", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_off(hass, "light.test")

    mqtt_mock.async_publish.assert_called_once_with("test_light/set", "OFF", 0, False)

    # Ensure color gets scaled with brightness.
    await common.async_turn_on(hass, "light.test", rgb_color=[255, 128, 0])

    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgb", "1,0,0", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_on(hass, "light.test", brightness=255)

    # Should get the following MQTT messages.
    #    test_light/rgb: '255,128,0'
    #    test_light/set: 'ON'
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgb", "255,128,0", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()


async def test_on_command_rgbw(hass, mqtt_mock):
    """Test on command in RGBW brightness mode."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "command_topic": "test_light/set",
            "rgbw_command_topic": "test_light/rgbw",
        }
    }

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN

    await common.async_turn_on(hass, "light.test", brightness=127)

    # Should get the following MQTT messages.
    #    test_light/rgbw: '127,127,127,127'
    #    test_light/set: 'ON'
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgbw", "127,127,127,127", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_on(hass, "light.test", brightness=255)

    # Should get the following MQTT messages.
    #    test_light/rgbw: '255,255,255,255'
    #    test_light/set: 'ON'
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgbw", "255,255,255,255", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_on(hass, "light.test", brightness=1)

    # Should get the following MQTT messages.
    #    test_light/rgbw: '1,1,1,1'
    #    test_light/set: 'ON'
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgbw", "1,1,1,1", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_off(hass, "light.test")

    mqtt_mock.async_publish.assert_called_once_with("test_light/set", "OFF", 0, False)

    # Ensure color gets scaled with brightness.
    await common.async_turn_on(hass, "light.test", rgbw_color=[255, 128, 0, 16])

    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgbw", "1,0,0,0", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_on(hass, "light.test", brightness=255)

    # Should get the following MQTT messages.
    #    test_light/rgbw: '255,128,0'
    #    test_light/set: 'ON'
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgbw", "255,128,0,16", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()


async def test_on_command_rgbww(hass, mqtt_mock):
    """Test on command in RGBWW brightness mode."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "command_topic": "test_light/set",
            "rgbww_command_topic": "test_light/rgbww",
        }
    }

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN

    await common.async_turn_on(hass, "light.test", brightness=127)

    # Should get the following MQTT messages.
    #    test_light/rgbww: '127,127,127,127,127'
    #    test_light/set: 'ON'
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgbww", "127,127,127,127,127", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_on(hass, "light.test", brightness=255)

    # Should get the following MQTT messages.
    #    test_light/rgbww: '255,255,255,255,255'
    #    test_light/set: 'ON'
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgbww", "255,255,255,255,255", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_on(hass, "light.test", brightness=1)

    # Should get the following MQTT messages.
    #    test_light/rgbww: '1,1,1,1,1'
    #    test_light/set: 'ON'
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgbww", "1,1,1,1,1", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_off(hass, "light.test")

    mqtt_mock.async_publish.assert_called_once_with("test_light/set", "OFF", 0, False)

    # Ensure color gets scaled with brightness.
    await common.async_turn_on(hass, "light.test", rgbww_color=[255, 128, 0, 16, 32])

    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgbww", "1,0,0,0,0", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_on(hass, "light.test", brightness=255)

    # Should get the following MQTT messages.
    #    test_light/rgbww: '255,128,0,16,32'
    #    test_light/set: 'ON'
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgbww", "255,128,0,16,32", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()


async def test_on_command_rgb_template(hass, mqtt_mock):
    """Test on command in RGB brightness mode with RGB template."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "command_topic": "test_light/set",
            "rgb_command_topic": "test_light/rgb",
            "rgb_command_template": "{{ red }}/{{ green }}/{{ blue }}",
        }
    }

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN

    await common.async_turn_on(hass, "light.test", brightness=127)

    # Should get the following MQTT messages.
    #    test_light/rgb: '127/127/127'
    #    test_light/set: 'ON'
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgb", "127/127/127", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_off(hass, "light.test")

    mqtt_mock.async_publish.assert_called_once_with("test_light/set", "OFF", 0, False)


async def test_on_command_rgbw_template(hass, mqtt_mock):
    """Test on command in RGBW brightness mode with RGBW template."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "command_topic": "test_light/set",
            "rgbw_command_topic": "test_light/rgbw",
            "rgbw_command_template": "{{ red }}/{{ green }}/{{ blue }}/{{ white }}",
        }
    }

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN
    await common.async_turn_on(hass, "light.test", brightness=127)

    # Should get the following MQTT messages.
    #    test_light/rgb: '127/127/127/127'
    #    test_light/set: 'ON'
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgbw", "127/127/127/127", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_off(hass, "light.test")

    mqtt_mock.async_publish.assert_called_once_with("test_light/set", "OFF", 0, False)


async def test_on_command_rgbww_template(hass, mqtt_mock):
    """Test on command in RGBWW brightness mode with RGBWW template."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "command_topic": "test_light/set",
            "rgbww_command_topic": "test_light/rgbww",
            "rgbww_command_template": "{{ red }}/{{ green }}/{{ blue }}/{{ cold_white }}/{{ warm_white }}",
        }
    }

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN

    await common.async_turn_on(hass, "light.test", brightness=127)

    # Should get the following MQTT messages.
    #    test_light/rgb: '127/127/127/127/127'
    #    test_light/set: 'ON'
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/rgbww", "127/127/127/127/127", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_off(hass, "light.test")

    mqtt_mock.async_publish.assert_called_once_with("test_light/set", "OFF", 0, False)


async def test_on_command_white(hass, mqtt_mock):
    """Test sending commands for RGB + white light."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "command_topic": "tasmota_B94927/cmnd/POWER",
            "state_value_template": "{{ value_json.POWER }}",
            "payload_off": "OFF",
            "payload_on": "ON",
            "brightness_command_topic": "tasmota_B94927/cmnd/Dimmer",
            "brightness_scale": 100,
            "on_command_type": "brightness",
            "brightness_value_template": "{{ value_json.Dimmer }}",
            "rgb_command_topic": "tasmota_B94927/cmnd/Color2",
            "rgb_value_template": "{{value_json.Color.split(',')[0:3]|join(',')}}",
            "white_command_topic": "tasmota_B94927/cmnd/White",
            "white_scale": 100,
            "color_mode_value_template": "{% if value_json.White %} white {% else %} rgb {% endif %}",
            "qos": "0",
        }
    }
    color_modes = ["rgb", "white"]

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN
    assert state.attributes.get("brightness") is None
    assert state.attributes.get("rgb_color") is None
    assert state.attributes.get(light.ATTR_COLOR_MODE) is None
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes
    assert state.attributes.get(ATTR_ASSUMED_STATE)

    await common.async_turn_on(hass, "light.test", brightness=192)
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("tasmota_B94927/cmnd/Dimmer", "75", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_on(hass, "light.test", white=255)
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("tasmota_B94927/cmnd/White", "100", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_on(hass, "light.test", white=64)
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("tasmota_B94927/cmnd/White", "25", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_on(hass, "light.test")
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("tasmota_B94927/cmnd/Dimmer", "25", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_off(hass, "light.test")
    mqtt_mock.async_publish.assert_called_once_with(
        "tasmota_B94927/cmnd/POWER", "OFF", 0, False
    )


async def test_explicit_color_mode(hass, mqtt_mock):
    """Test explicit color mode over mqtt."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "state_topic": "test_light_rgb/status",
            "command_topic": "test_light_rgb/set",
            "color_mode_state_topic": "test_light_rgb/color_mode/status",
            "brightness_state_topic": "test_light_rgb/brightness/status",
            "brightness_command_topic": "test_light_rgb/brightness/set",
            "rgb_state_topic": "test_light_rgb/rgb/status",
            "rgb_command_topic": "test_light_rgb/rgb/set",
            "rgbw_state_topic": "test_light_rgb/rgbw/status",
            "rgbw_command_topic": "test_light_rgb/rgbw/set",
            "rgbww_state_topic": "test_light_rgb/rgbww/status",
            "rgbww_command_topic": "test_light_rgb/rgbww/set",
            "color_temp_state_topic": "test_light_rgb/color_temp/status",
            "color_temp_command_topic": "test_light_rgb/color_temp/set",
            "effect_state_topic": "test_light_rgb/effect/status",
            "effect_command_topic": "test_light_rgb/effect/set",
            "hs_state_topic": "test_light_rgb/hs/status",
            "hs_command_topic": "test_light_rgb/hs/set",
            "xy_state_topic": "test_light_rgb/xy/status",
            "xy_command_topic": "test_light_rgb/xy/set",
            "qos": "0",
            "payload_on": 1,
            "payload_off": 0,
        }
    }
    color_modes = ["color_temp", "hs", "rgb", "rgbw", "rgbww", "xy"]

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN
    assert state.attributes.get("rgb_color") is None
    assert state.attributes.get("brightness") is None
    assert state.attributes.get("color_temp") is None
    assert state.attributes.get("effect") is None
    assert state.attributes.get("hs_color") is None
    assert state.attributes.get("rgb_color") is None
    assert state.attributes.get("rgbw_color") is None
    assert state.attributes.get("rgbww_color") is None
    assert state.attributes.get("white_value") is None
    assert state.attributes.get("xy_color") is None
    assert state.attributes.get(light.ATTR_COLOR_MODE) is None
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes
    assert not state.attributes.get(ATTR_ASSUMED_STATE)

    async_fire_mqtt_message(hass, "test_light_rgb/status", "1")
    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("rgb_color") is None
    assert state.attributes.get("brightness") is None
    assert state.attributes.get("color_temp") is None
    assert state.attributes.get("effect") is None
    assert state.attributes.get("hs_color") is None
    assert state.attributes.get("rgb_color") is None
    assert state.attributes.get("rgbw_color") is None
    assert state.attributes.get("rgbww_color") is None
    assert state.attributes.get("white_value") is None
    assert state.attributes.get("xy_color") is None
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "unknown"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/status", "0")
    state = hass.states.get("light.test")
    assert state.state == STATE_OFF

    async_fire_mqtt_message(hass, "test_light_rgb/status", "1")
    async_fire_mqtt_message(hass, "test_light_rgb/brightness/status", "100")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("brightness") is None
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "unknown"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/color_temp/status", "300")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "unknown"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/effect/status", "rainbow")
    light_state = hass.states.get("light.test")
    assert light_state.attributes["effect"] == "rainbow"
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "unknown"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/rgb/status", "125,125,125")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "unknown"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/rgbw/status", "80,40,20,10")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "unknown"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/rgbww/status", "80,40,20,10,8")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "unknown"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/hs/status", "200,50")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "unknown"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/xy/status", "0.675,0.322")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "unknown"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/color_mode/status", "color_temp")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "color_temp"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/color_mode/status", "rgb")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("rgb_color") == (125, 125, 125)
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "rgb"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/color_mode/status", "rgbw")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("rgbw_color") == (80, 40, 20, 10)
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "rgbw"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/color_mode/status", "rgbww")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("rgbww_color") == (80, 40, 20, 10, 8)
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "rgbww"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/color_mode/status", "hs")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("hs_color") == (200, 50)
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "hs"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/color_mode/status", "xy")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("xy_color") == (0.675, 0.322)
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "xy"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes


async def test_explicit_color_mode_templated(hass, mqtt_mock):
    """Test templated explicit color mode over mqtt."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "state_topic": "test_light_rgb/status",
            "command_topic": "test_light_rgb/set",
            "color_mode_state_topic": "test_light_rgb/color_mode/status",
            "color_mode_value_template": "{{ value_json.color_mode }}",
            "brightness_state_topic": "test_light_rgb/brightness/status",
            "brightness_command_topic": "test_light_rgb/brightness/set",
            "color_temp_state_topic": "test_light_rgb/color_temp/status",
            "color_temp_command_topic": "test_light_rgb/color_temp/set",
            "hs_state_topic": "test_light_rgb/hs/status",
            "hs_command_topic": "test_light_rgb/hs/set",
            "qos": "0",
            "payload_on": 1,
            "payload_off": 0,
        }
    }
    color_modes = ["color_temp", "hs"]

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN
    assert state.attributes.get("brightness") is None
    assert state.attributes.get("color_temp") is None
    assert state.attributes.get("hs_color") is None
    assert state.attributes.get(light.ATTR_COLOR_MODE) is None
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes
    assert not state.attributes.get(ATTR_ASSUMED_STATE)

    async_fire_mqtt_message(hass, "test_light_rgb/status", "1")
    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("brightness") is None
    assert state.attributes.get("color_temp") is None
    assert state.attributes.get("hs_color") is None
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "unknown"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/status", "0")
    state = hass.states.get("light.test")
    assert state.state == STATE_OFF

    async_fire_mqtt_message(hass, "test_light_rgb/status", "1")
    async_fire_mqtt_message(hass, "test_light_rgb/brightness/status", "100")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("brightness") is None
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "unknown"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/color_temp/status", "300")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "unknown"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(hass, "test_light_rgb/hs/status", "200,50")
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "unknown"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(
        hass, "test_light_rgb/color_mode/status", '{"color_mode":"color_temp"}'
    )
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "color_temp"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(
        hass, "test_light_rgb/color_mode/status", '{"color_mode":"hs"}'
    )
    light_state = hass.states.get("light.test")
    assert light_state.attributes.get("hs_color") == (200, 50)
    assert light_state.attributes.get(light.ATTR_COLOR_MODE) == "hs"
    assert light_state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes


async def test_white_state_update(hass, mqtt_mock):
    """Test state updates for RGB + white light."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "state_topic": "tasmota_B94927/tele/STATE",
            "command_topic": "tasmota_B94927/cmnd/POWER",
            "state_value_template": "{{ value_json.POWER }}",
            "payload_off": "OFF",
            "payload_on": "ON",
            "brightness_command_topic": "tasmota_B94927/cmnd/Dimmer",
            "brightness_state_topic": "tasmota_B94927/tele/STATE",
            "brightness_scale": 100,
            "on_command_type": "brightness",
            "brightness_value_template": "{{ value_json.Dimmer }}",
            "rgb_command_topic": "tasmota_B94927/cmnd/Color2",
            "rgb_state_topic": "tasmota_B94927/tele/STATE",
            "rgb_value_template": "{{value_json.Color.split(',')[0:3]|join(',')}}",
            "white_command_topic": "tasmota_B94927/cmnd/White",
            "white_scale": 100,
            "color_mode_state_topic": "tasmota_B94927/tele/STATE",
            "color_mode_value_template": "{% if value_json.White %} white {% else %} rgb {% endif %}",
            "qos": "0",
        }
    }
    color_modes = ["rgb", "white"]

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN
    assert state.attributes.get("brightness") is None
    assert state.attributes.get("rgb_color") is None
    assert state.attributes.get(light.ATTR_COLOR_MODE) is None
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes
    assert not state.attributes.get(ATTR_ASSUMED_STATE)

    async_fire_mqtt_message(
        hass,
        "tasmota_B94927/tele/STATE",
        '{"POWER":"ON","Dimmer":50,"Color":"0,0,0,128","White":50}',
    )
    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("brightness") == 128
    assert state.attributes.get("rgb_color") is None
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "white"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes

    async_fire_mqtt_message(
        hass,
        "tasmota_B94927/tele/STATE",
        '{"POWER":"ON","Dimmer":50,"Color":"128,64,32,0","White":0}',
    )
    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("brightness") == 128
    assert state.attributes.get("rgb_color") == (128, 64, 32)
    assert state.attributes.get(light.ATTR_COLOR_MODE) == "rgb"
    assert state.attributes.get(light.ATTR_SUPPORTED_COLOR_MODES) == color_modes


async def test_effect(hass, mqtt_mock):
    """Test effect."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "command_topic": "test_light/set",
            "effect_command_topic": "test_light/effect/set",
            "effect_list": ["rainbow", "colorloop"],
        }
    }

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN

    await common.async_turn_on(hass, "light.test", effect="rainbow")

    # Should get the following MQTT messages.
    #    test_light/effect/set: 'rainbow'
    #    test_light/set: 'ON'
    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light/effect/set", "rainbow", 0, False),
            call("test_light/set", "ON", 0, False),
        ],
        any_order=True,
    )
    mqtt_mock.async_publish.reset_mock()

    await common.async_turn_off(hass, "light.test")

    mqtt_mock.async_publish.assert_called_once_with("test_light/set", "OFF", 0, False)


async def test_availability_when_connection_lost(hass, mqtt_mock):
    """Test availability after MQTT disconnection."""
    await help_test_availability_when_connection_lost(
        hass, mqtt_mock, light.DOMAIN, DEFAULT_CONFIG
    )


async def test_availability_without_topic(hass, mqtt_mock):
    """Test availability without defined availability topic."""
    await help_test_availability_without_topic(
        hass, mqtt_mock, light.DOMAIN, DEFAULT_CONFIG
    )


async def test_default_availability_payload(hass, mqtt_mock):
    """Test availability by default payload with defined topic."""
    await help_test_default_availability_payload(
        hass, mqtt_mock, light.DOMAIN, DEFAULT_CONFIG
    )


async def test_custom_availability_payload(hass, mqtt_mock):
    """Test availability by custom payload with defined topic."""
    await help_test_custom_availability_payload(
        hass, mqtt_mock, light.DOMAIN, DEFAULT_CONFIG
    )


async def test_setting_attribute_via_mqtt_json_message(hass, mqtt_mock):
    """Test the setting of attribute via MQTT with JSON payload."""
    await help_test_setting_attribute_via_mqtt_json_message(
        hass, mqtt_mock, light.DOMAIN, DEFAULT_CONFIG
    )


async def test_setting_blocked_attribute_via_mqtt_json_message(hass, mqtt_mock):
    """Test the setting of attribute via MQTT with JSON payload."""
    await help_test_setting_blocked_attribute_via_mqtt_json_message(
        hass, mqtt_mock, light.DOMAIN, DEFAULT_CONFIG, MQTT_LIGHT_ATTRIBUTES_BLOCKED
    )


async def test_setting_attribute_with_template(hass, mqtt_mock):
    """Test the setting of attribute via MQTT with JSON payload."""
    await help_test_setting_attribute_with_template(
        hass, mqtt_mock, light.DOMAIN, DEFAULT_CONFIG
    )


async def test_update_with_json_attrs_not_dict(hass, mqtt_mock, caplog):
    """Test attributes get extracted from a JSON result."""
    await help_test_update_with_json_attrs_not_dict(
        hass, mqtt_mock, caplog, light.DOMAIN, DEFAULT_CONFIG
    )


async def test_update_with_json_attrs_bad_JSON(hass, mqtt_mock, caplog):
    """Test attributes get extracted from a JSON result."""
    await help_test_update_with_json_attrs_bad_JSON(
        hass, mqtt_mock, caplog, light.DOMAIN, DEFAULT_CONFIG
    )


async def test_discovery_update_attr(hass, mqtt_mock, caplog):
    """Test update of discovered MQTTAttributes."""
    await help_test_discovery_update_attr(
        hass, mqtt_mock, caplog, light.DOMAIN, DEFAULT_CONFIG
    )


async def test_unique_id(hass, mqtt_mock):
    """Test unique id option only creates one light per unique_id."""
    config = {
        light.DOMAIN: [
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
    await help_test_unique_id(hass, mqtt_mock, light.DOMAIN, config)


async def test_discovery_removal_light(hass, mqtt_mock, caplog):
    """Test removal of discovered light."""
    data = (
        '{ "name": "test",'
        '  "state_topic": "test_topic",'
        '  "command_topic": "test_topic" }'
    )
    await help_test_discovery_removal(hass, mqtt_mock, caplog, light.DOMAIN, data)


async def test_discovery_deprecated(hass, mqtt_mock, caplog):
    """Test discovery of mqtt light with deprecated platform option."""
    data = (
        '{ "name": "Beer",' '  "platform": "mqtt",' '  "command_topic": "test_topic"}'
    )
    async_fire_mqtt_message(hass, "homeassistant/light/bla/config", data)
    await hass.async_block_till_done()
    state = hass.states.get("light.beer")
    assert state is not None
    assert state.name == "Beer"


async def test_discovery_update_light_topic_and_template(hass, mqtt_mock, caplog):
    """Test update of discovered light."""
    config1 = {
        "name": "Beer",
        "state_topic": "test_light_rgb/state1",
        "command_topic": "test_light_rgb/set",
        "brightness_command_topic": "test_light_rgb/state1",
        "rgb_command_topic": "test_light_rgb/rgb/set",
        "color_temp_command_topic": "test_light_rgb/state1",
        "effect_command_topic": "test_light_rgb/effect/set",
        "hs_command_topic": "test_light_rgb/hs/set",
        "white_value_command_topic": "test_light_rgb/white_value/set",
        "xy_command_topic": "test_light_rgb/xy/set",
        "brightness_state_topic": "test_light_rgb/state1",
        "color_temp_state_topic": "test_light_rgb/state1",
        "effect_state_topic": "test_light_rgb/state1",
        "hs_state_topic": "test_light_rgb/state1",
        "rgb_state_topic": "test_light_rgb/state1",
        "white_value_state_topic": "test_light_rgb/state1",
        "xy_state_topic": "test_light_rgb/state1",
        "state_value_template": "{{ value_json.state1.state }}",
        "brightness_value_template": "{{ value_json.state1.brightness }}",
        "color_temp_value_template": "{{ value_json.state1.ct }}",
        "effect_value_template": "{{ value_json.state1.fx }}",
        "hs_value_template": "{{ value_json.state1.hs }}",
        "rgb_value_template": "{{ value_json.state1.rgb }}",
        "white_value_template": "{{ value_json.state1.white }}",
        "xy_value_template": "{{ value_json.state1.xy }}",
    }

    config2 = {
        "name": "Milk",
        "state_topic": "test_light_rgb/state2",
        "command_topic": "test_light_rgb/set",
        "brightness_command_topic": "test_light_rgb/state2",
        "rgb_command_topic": "test_light_rgb/rgb/set",
        "color_temp_command_topic": "test_light_rgb/state2",
        "effect_command_topic": "test_light_rgb/effect/set",
        "hs_command_topic": "test_light_rgb/hs/set",
        "white_value_command_topic": "test_light_rgb/white_value/set",
        "xy_command_topic": "test_light_rgb/xy/set",
        "brightness_state_topic": "test_light_rgb/state2",
        "color_temp_state_topic": "test_light_rgb/state2",
        "effect_state_topic": "test_light_rgb/state2",
        "hs_state_topic": "test_light_rgb/state2",
        "rgb_state_topic": "test_light_rgb/state2",
        "white_value_state_topic": "test_light_rgb/state2",
        "xy_state_topic": "test_light_rgb/state2",
        "state_value_template": "{{ value_json.state2.state }}",
        "brightness_value_template": "{{ value_json.state2.brightness }}",
        "color_temp_value_template": "{{ value_json.state2.ct }}",
        "effect_value_template": "{{ value_json.state2.fx }}",
        "hs_value_template": "{{ value_json.state2.hs }}",
        "rgb_value_template": "{{ value_json.state2.rgb }}",
        "white_value_template": "{{ value_json.state2.white }}",
        "xy_value_template": "{{ value_json.state2.xy }}",
    }
    state_data1 = [
        (
            [
                (
                    "test_light_rgb/state1",
                    '{"state1":{"state":"ON", "brightness":100, "ct":123, "white":100, "fx":"cycle"}}',
                )
            ],
            "on",
            [
                ("brightness", 100),
                ("color_temp", 123),
                ("white_value", 100),
                ("effect", "cycle"),
            ],
        ),
        (
            [("test_light_rgb/state1", '{"state1":{"state":"OFF"}}')],
            "off",
            None,
        ),
        (
            [
                (
                    "test_light_rgb/state1",
                    '{"state1":{"state":"ON", "hs":"1,2", "white":0}}',
                )
            ],
            "on",
            [("hs_color", (1, 2)), ("white_value", None)],
        ),
        (
            [
                (
                    "test_light_rgb/state1",
                    '{"state1":{"rgb":"255,127,63"}}',
                )
            ],
            "on",
            [("rgb_color", (255, 127, 63))],
        ),
        (
            [
                (
                    "test_light_rgb/state1",
                    '{"state1":{"xy":"0.3, 0.4"}}',
                )
            ],
            "on",
            [("xy_color", (0.3, 0.401))],
        ),
    ]
    state_data2 = [
        (
            [
                (
                    "test_light_rgb/state2",
                    '{"state2":{"state":"ON", "brightness":50, "ct":200, "white":50, "fx":"loop"}}',
                )
            ],
            "on",
            [
                ("brightness", 50),
                ("color_temp", 200),
                ("white_value", 50),
                ("effect", "loop"),
            ],
        ),
        (
            [
                (
                    "test_light_rgb/state1",
                    '{"state1":{"state":"ON", "brightness":100, "ct":123, "fx":"cycle"}}',
                ),
                (
                    "test_light_rgb/state1",
                    '{"state2":{"state":"ON", "brightness":100, "ct":123, "fx":"cycle"}}',
                ),
                (
                    "test_light_rgb/state2",
                    '{"state1":{"state":"ON", "brightness":100, "ct":123, "fx":"cycle"}}',
                ),
            ],
            "on",
            [("brightness", 50), ("color_temp", 200), ("effect", "loop")],
        ),
        (
            [("test_light_rgb/state1", '{"state1":{"state":"OFF"}}')],
            "on",
            None,
        ),
        (
            [("test_light_rgb/state1", '{"state2":{"state":"OFF"}}')],
            "on",
            None,
        ),
        (
            [("test_light_rgb/state2", '{"state1":{"state":"OFF"}}')],
            "on",
            None,
        ),
        (
            [("test_light_rgb/state2", '{"state2":{"state":"OFF"}}')],
            "off",
            None,
        ),
        (
            [
                (
                    "test_light_rgb/state2",
                    '{"state2":{"state":"ON", "hs":"1.2,2.2", "white":0}}',
                )
            ],
            "on",
            [("hs_color", (1.2, 2.2)), ("white_value", None)],
        ),
        (
            [
                (
                    "test_light_rgb/state1",
                    '{"state1":{"state":"ON", "hs":"1,2"}}',
                ),
                (
                    "test_light_rgb/state1",
                    '{"state2":{"state":"ON", "hs":"1,2"}}',
                ),
                (
                    "test_light_rgb/state2",
                    '{"state1":{"state":"ON", "hs":"1,2"}}',
                ),
            ],
            "on",
            [("hs_color", (1.2, 2.2))],
        ),
        (
            [
                (
                    "test_light_rgb/state2",
                    '{"state2":{"rgb":"63,127,255"}}',
                )
            ],
            "on",
            [("rgb_color", (63, 127, 255))],
        ),
        (
            [
                (
                    "test_light_rgb/state1",
                    '{"state1":{"rgb":"255,127,63"}}',
                ),
                (
                    "test_light_rgb/state1",
                    '{"state2":{"rgb":"255,127,63"}}',
                ),
                (
                    "test_light_rgb/state2",
                    '{"state1":{"rgb":"255,127,63"}}',
                ),
            ],
            "on",
            [("rgb_color", (63, 127, 255))],
        ),
        (
            [
                (
                    "test_light_rgb/state2",
                    '{"state2":{"xy":"0.4, 0.3"}}',
                )
            ],
            "on",
            [("xy_color", (0.4, 0.3))],
        ),
        (
            [
                (
                    "test_light_rgb/state1",
                    '{"state1":{"white":50, "xy":"0.3, 0.4"}}',
                ),
                (
                    "test_light_rgb/state1",
                    '{"state2":{"white":50, "xy":"0.3, 0.4"}}',
                ),
                (
                    "test_light_rgb/state2",
                    '{"state1":{"white":50, "xy":"0.3, 0.4"}}',
                ),
            ],
            "on",
            [("xy_color", (0.4, 0.3))],
        ),
    ]

    await help_test_discovery_update(
        hass,
        mqtt_mock,
        caplog,
        light.DOMAIN,
        config1,
        config2,
        state_data1=state_data1,
        state_data2=state_data2,
    )


async def test_discovery_update_light_template(hass, mqtt_mock, caplog):
    """Test update of discovered light."""
    config1 = {
        "name": "Beer",
        "state_topic": "test_light_rgb/state1",
        "command_topic": "test_light_rgb/set",
        "brightness_command_topic": "test_light_rgb/state1",
        "rgb_command_topic": "test_light_rgb/rgb/set",
        "color_temp_command_topic": "test_light_rgb/state1",
        "effect_command_topic": "test_light_rgb/effect/set",
        "hs_command_topic": "test_light_rgb/hs/set",
        "white_value_command_topic": "test_light_rgb/white_value/set",
        "xy_command_topic": "test_light_rgb/xy/set",
        "brightness_state_topic": "test_light_rgb/state1",
        "color_temp_state_topic": "test_light_rgb/state1",
        "effect_state_topic": "test_light_rgb/state1",
        "hs_state_topic": "test_light_rgb/state1",
        "rgb_state_topic": "test_light_rgb/state1",
        "white_value_state_topic": "test_light_rgb/state1",
        "xy_state_topic": "test_light_rgb/state1",
        "state_value_template": "{{ value_json.state1.state }}",
        "brightness_value_template": "{{ value_json.state1.brightness }}",
        "color_temp_value_template": "{{ value_json.state1.ct }}",
        "effect_value_template": "{{ value_json.state1.fx }}",
        "hs_value_template": "{{ value_json.state1.hs }}",
        "rgb_value_template": "{{ value_json.state1.rgb }}",
        "white_value_template": "{{ value_json.state1.white }}",
        "xy_value_template": "{{ value_json.state1.xy }}",
    }

    config2 = {
        "name": "Milk",
        "state_topic": "test_light_rgb/state1",
        "command_topic": "test_light_rgb/set",
        "brightness_command_topic": "test_light_rgb/state1",
        "rgb_command_topic": "test_light_rgb/rgb/set",
        "color_temp_command_topic": "test_light_rgb/state1",
        "effect_command_topic": "test_light_rgb/effect/set",
        "hs_command_topic": "test_light_rgb/hs/set",
        "white_value_command_topic": "test_light_rgb/white_value/set",
        "xy_command_topic": "test_light_rgb/xy/set",
        "brightness_state_topic": "test_light_rgb/state1",
        "color_temp_state_topic": "test_light_rgb/state1",
        "effect_state_topic": "test_light_rgb/state1",
        "hs_state_topic": "test_light_rgb/state1",
        "rgb_state_topic": "test_light_rgb/state1",
        "white_value_state_topic": "test_light_rgb/state1",
        "xy_state_topic": "test_light_rgb/state1",
        "state_value_template": "{{ value_json.state2.state }}",
        "brightness_value_template": "{{ value_json.state2.brightness }}",
        "color_temp_value_template": "{{ value_json.state2.ct }}",
        "effect_value_template": "{{ value_json.state2.fx }}",
        "hs_value_template": "{{ value_json.state2.hs }}",
        "rgb_value_template": "{{ value_json.state2.rgb }}",
        "white_value_template": "{{ value_json.state2.white }}",
        "xy_value_template": "{{ value_json.state2.xy }}",
    }
    state_data1 = [
        (
            [
                (
                    "test_light_rgb/state1",
                    '{"state1":{"state":"ON", "brightness":100, "ct":123, "white":100, "fx":"cycle"}}',
                )
            ],
            "on",
            [
                ("brightness", 100),
                ("color_temp", 123),
                ("white_value", 100),
                ("effect", "cycle"),
            ],
        ),
        (
            [("test_light_rgb/state1", '{"state1":{"state":"OFF"}}')],
            "off",
            None,
        ),
        (
            [
                (
                    "test_light_rgb/state1",
                    '{"state1":{"state":"ON", "hs":"1,2", "white":0}}',
                )
            ],
            "on",
            [("hs_color", (1, 2))],
        ),
        (
            [
                (
                    "test_light_rgb/state1",
                    '{"state1":{"rgb":"255,127,63"}}',
                )
            ],
            "on",
            [("rgb_color", (255, 127, 63))],
        ),
        (
            [
                (
                    "test_light_rgb/state1",
                    '{"state1":{"white":0, "xy":"0.3, 0.4"}}',
                )
            ],
            "on",
            [("white_value", None), ("xy_color", (0.3, 0.401))],
        ),
    ]
    state_data2 = [
        (
            [
                (
                    "test_light_rgb/state1",
                    '{"state2":{"state":"ON", "brightness":50, "ct":200, "white":50, "fx":"loop"}}',
                )
            ],
            "on",
            [
                ("brightness", 50),
                ("color_temp", 200),
                ("white_value", 50),
                ("effect", "loop"),
            ],
        ),
        (
            [
                (
                    "test_light_rgb/state1",
                    '{"state1":{"state":"ON", "brightness":100, "ct":123, "fx":"cycle"}}',
                ),
            ],
            "on",
            [("brightness", 50), ("color_temp", 200), ("effect", "loop")],
        ),
        (
            [("test_light_rgb/state1", '{"state1":{"state":"OFF"}}')],
            "on",
            None,
        ),
        (
            [("test_light_rgb/state1", '{"state2":{"state":"OFF"}}')],
            "off",
            None,
        ),
        (
            [
                (
                    "test_light_rgb/state1",
                    '{"state2":{"state":"ON", "hs":"1.2,2.2", "white":0}}',
                )
            ],
            "on",
            [("hs_color", (1.2, 2.2))],
        ),
        (
            [
                (
                    "test_light_rgb/state1",
                    '{"state1":{"state":"ON", "hs":"1,2"}}',
                )
            ],
            "on",
            [("hs_color", (1.2, 2.2))],
        ),
        (
            [
                (
                    "test_light_rgb/state1",
                    '{"state2":{"rgb":"63,127,255"}}',
                )
            ],
            "on",
            [("rgb_color", (63, 127, 255))],
        ),
        (
            [
                (
                    "test_light_rgb/state1",
                    '{"state1":{"rgb":"255,127,63"}}',
                )
            ],
            "on",
            [("rgb_color", (63, 127, 255))],
        ),
        (
            [
                (
                    "test_light_rgb/state1",
                    '{"state2":{"xy":"0.4, 0.3"}}',
                )
            ],
            "on",
            [("white_value", None), ("xy_color", (0.4, 0.3))],
        ),
        (
            [
                (
                    "test_light_rgb/state1",
                    '{"state1":{"white":50, "xy":"0.3, 0.4"}}',
                )
            ],
            "on",
            [("white_value", None), ("xy_color", (0.4, 0.3))],
        ),
    ]

    await help_test_discovery_update(
        hass,
        mqtt_mock,
        caplog,
        light.DOMAIN,
        config1,
        config2,
        state_data1=state_data1,
        state_data2=state_data2,
    )


async def test_discovery_update_unchanged_light(hass, mqtt_mock, caplog):
    """Test update of discovered light."""
    data1 = (
        '{ "name": "Beer",'
        '  "state_topic": "test_topic",'
        '  "command_topic": "test_topic" }'
    )
    with patch(
        "homeassistant.components.mqtt.light.schema_basic.MqttLight.discovery_update"
    ) as discovery_update:
        await help_test_discovery_update_unchanged(
            hass, mqtt_mock, caplog, light.DOMAIN, data1, discovery_update
        )


@pytest.mark.no_fail_on_log_exception
async def test_discovery_broken(hass, mqtt_mock, caplog):
    """Test handling of bad discovery message."""
    data1 = '{ "name": "Beer" }'
    data2 = (
        '{ "name": "Milk",'
        '  "state_topic": "test_topic",'
        '  "command_topic": "test_topic" }'
    )
    await help_test_discovery_broken(
        hass, mqtt_mock, caplog, light.DOMAIN, data1, data2
    )


async def test_entity_device_info_with_connection(hass, mqtt_mock):
    """Test MQTT light device registry integration."""
    await help_test_entity_device_info_with_connection(
        hass, mqtt_mock, light.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_device_info_with_identifier(hass, mqtt_mock):
    """Test MQTT light device registry integration."""
    await help_test_entity_device_info_with_identifier(
        hass, mqtt_mock, light.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_device_info_update(hass, mqtt_mock):
    """Test device registry update."""
    await help_test_entity_device_info_update(
        hass, mqtt_mock, light.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_device_info_remove(hass, mqtt_mock):
    """Test device registry remove."""
    await help_test_entity_device_info_remove(
        hass, mqtt_mock, light.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_id_update_subscriptions(hass, mqtt_mock):
    """Test MQTT subscriptions are managed when entity_id is updated."""
    await help_test_entity_id_update_subscriptions(
        hass, mqtt_mock, light.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_id_update_discovery_update(hass, mqtt_mock):
    """Test MQTT discovery update when entity_id is updated."""
    await help_test_entity_id_update_discovery_update(
        hass, mqtt_mock, light.DOMAIN, DEFAULT_CONFIG
    )


async def test_entity_debug_info_message(hass, mqtt_mock):
    """Test MQTT debug info."""
    await help_test_entity_debug_info_message(
        hass, mqtt_mock, light.DOMAIN, DEFAULT_CONFIG, light.SERVICE_TURN_ON
    )


async def test_max_mireds(hass, mqtt_mock):
    """Test setting min_mireds and max_mireds."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "command_topic": "test_max_mireds/set",
            "color_temp_command_topic": "test_max_mireds/color_temp/set",
            "max_mireds": 370,
        }
    }

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.attributes.get("min_mireds") == 153
    assert state.attributes.get("max_mireds") == 370


@pytest.mark.parametrize(
    "service,topic,parameters,payload,template,tpl_par,tpl_output",
    [
        (
            light.SERVICE_TURN_ON,
            "command_topic",
            None,
            "ON",
            None,
            None,
            None,
        ),
        (
            light.SERVICE_TURN_ON,
            "white_command_topic",
            {"white": "255"},
            255,
            None,
            None,
            None,
        ),
        (
            light.SERVICE_TURN_ON,
            "brightness_command_topic",
            {"color_temp": "200", "brightness": "50"},
            50,
            "brightness_command_template",
            "value",
            b"5",
        ),
        (
            light.SERVICE_TURN_ON,
            "effect_command_topic",
            {"rgb_color": [255, 128, 0], "effect": "color_loop"},
            "color_loop",
            "effect_command_template",
            "value",
            b"c",
        ),
        (
            light.SERVICE_TURN_ON,
            "color_temp_command_topic",
            {"color_temp": "200"},
            200,
            "color_temp_command_template",
            "value",
            b"2",
        ),
        (
            light.SERVICE_TURN_ON,
            "rgb_command_topic",
            {"rgb_color": [255, 128, 0]},
            "255,128,0",
            "rgb_command_template",
            "red",
            b"2",
        ),
        (
            light.SERVICE_TURN_ON,
            "hs_command_topic",
            {"rgb_color": [255, 128, 0]},
            "30.118,100.0",
            None,
            None,
            None,
        ),
        (
            light.SERVICE_TURN_ON,
            "xy_command_topic",
            {"hs_color": [30.118, 100.0]},
            "0.611,0.375",
            None,
            None,
            None,
        ),
        (
            light.SERVICE_TURN_OFF,
            "command_topic",
            None,
            "OFF",
            None,
            None,
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
    tpl_par,
    tpl_output,
):
    """Test publishing MQTT payload with different encoding."""
    domain = light.DOMAIN
    config = copy.deepcopy(DEFAULT_CONFIG[domain])
    if topic == "effect_command_topic":
        config["effect_list"] = ["random", "color_loop"]
    elif topic == "white_command_topic":
        config["rgb_command_topic"] = "some-cmd-topic"

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
        tpl_par=tpl_par,
        tpl_output=tpl_output,
    )


async def test_reloadable(hass, mqtt_mock, caplog, tmp_path):
    """Test reloading the MQTT platform."""
    domain = light.DOMAIN
    config = DEFAULT_CONFIG[domain]
    await help_test_reloadable(hass, mqtt_mock, caplog, tmp_path, domain, config)


async def test_reloadable_late(hass, mqtt_client_mock, caplog, tmp_path):
    """Test reloading the MQTT platform with late entry setup."""
    domain = light.DOMAIN
    config = DEFAULT_CONFIG[domain]
    await help_test_reloadable_late(hass, caplog, tmp_path, domain, config)


@pytest.mark.parametrize(
    "topic,value,attribute,attribute_value,init_payload",
    [
        ("state_topic", "ON", None, "on", None),
        ("brightness_state_topic", "60", "brightness", 60, ("state_topic", "ON")),
        (
            "color_mode_state_topic",
            "200",
            "color_mode",
            "200",
            ("state_topic", "ON"),
        ),
        ("color_temp_state_topic", "200", "color_temp", 200, ("state_topic", "ON")),
        ("effect_state_topic", "random", "effect", "random", ("state_topic", "ON")),
        ("hs_state_topic", "200,50", "hs_color", (200, 50), ("state_topic", "ON")),
        (
            "xy_state_topic",
            "128,128",
            "xy_color",
            (128, 128),
            ("state_topic", "ON"),
        ),
        (
            "rgb_state_topic",
            "255,0,240",
            "rgb_color",
            (255, 0, 240),
            ("state_topic", "ON"),
        ),
    ],
)
async def test_encoding_subscribable_topics(
    hass, mqtt_mock, caplog, topic, value, attribute, attribute_value, init_payload
):
    """Test handling of incoming encoded payload."""
    config = copy.deepcopy(DEFAULT_CONFIG[light.DOMAIN])
    config[CONF_EFFECT_COMMAND_TOPIC] = "light/CONF_EFFECT_COMMAND_TOPIC"
    config[CONF_RGB_COMMAND_TOPIC] = "light/CONF_RGB_COMMAND_TOPIC"
    config[CONF_BRIGHTNESS_COMMAND_TOPIC] = "light/CONF_BRIGHTNESS_COMMAND_TOPIC"
    config[CONF_COLOR_TEMP_COMMAND_TOPIC] = "light/CONF_COLOR_TEMP_COMMAND_TOPIC"
    config[CONF_HS_COMMAND_TOPIC] = "light/CONF_HS_COMMAND_TOPIC"
    config[CONF_RGB_COMMAND_TOPIC] = "light/CONF_RGB_COMMAND_TOPIC"
    config[CONF_RGBW_COMMAND_TOPIC] = "light/CONF_RGBW_COMMAND_TOPIC"
    config[CONF_RGBWW_COMMAND_TOPIC] = "light/CONF_RGBWW_COMMAND_TOPIC"
    config[CONF_XY_COMMAND_TOPIC] = "light/CONF_XY_COMMAND_TOPIC"
    config[CONF_EFFECT_LIST] = ["colorloop", "random"]
    if attribute and attribute == "brightness":
        config[CONF_WHITE_VALUE_COMMAND_TOPIC] = "light/CONF_WHITE_VALUE_COMMAND_TOPIC"

    await help_test_encoding_subscribable_topics(
        hass,
        mqtt_mock,
        caplog,
        light.DOMAIN,
        config,
        topic,
        value,
        attribute,
        attribute_value,
        init_payload,
    )


async def test_sending_mqtt_brightness_command_with_template(hass, mqtt_mock):
    """Test the sending of Brightness command with template."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "command_topic": "test_light_brightness/set",
            "brightness_command_topic": "test_light_brightness/brightness/set",
            "brightness_command_template": "{{ (1000 / value) | round(0) }}",
            "payload_on": "on",
            "payload_off": "off",
            "qos": 0,
        }
    }

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN

    await common.async_turn_on(hass, "light.test", brightness=100)

    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light_brightness/set", "on", 0, False),
            call("test_light_brightness/brightness/set", "10", 0, False),
        ],
        any_order=True,
    )

    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes["brightness"] == 100


async def test_sending_mqtt_effect_command_with_template(hass, mqtt_mock):
    """Test the sending of Effect command with template."""
    config = {
        light.DOMAIN: {
            "platform": "mqtt",
            "name": "test",
            "command_topic": "test_light_brightness/set",
            "brightness_command_topic": "test_light_brightness/brightness/set",
            "effect_command_topic": "test_light_brightness/effect/set",
            "effect_command_template": '{ "effect": "{{ value }}" }',
            "effect_list": ["colorloop", "random"],
            "payload_on": "on",
            "payload_off": "off",
            "qos": 0,
        }
    }

    assert await async_setup_component(hass, light.DOMAIN, config)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state.state == STATE_UNKNOWN

    await common.async_turn_on(hass, "light.test", effect="colorloop")

    mqtt_mock.async_publish.assert_has_calls(
        [
            call("test_light_brightness/set", "on", 0, False),
            call(
                "test_light_brightness/effect/set",
                '{ "effect": "colorloop" }',
                0,
                False,
            ),
        ],
        any_order=True,
    )
    state = hass.states.get("light.test")
    assert state.state == STATE_ON
    assert state.attributes.get("effect") == "colorloop"
