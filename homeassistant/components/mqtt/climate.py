"""Support for MQTT climate devices."""
from __future__ import annotations

import functools
import logging

import voluptuous as vol

from homeassistant.components import climate
from homeassistant.components.climate import (
    PLATFORM_SCHEMA as CLIMATE_PLATFORM_SCHEMA,
    ClimateEntity,
    ClimateEntityFeature,
)
from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    CURRENT_HVAC_ACTIONS,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    HVAC_MODE_AUTO,
    HVAC_MODE_COOL,
    HVAC_MODE_DRY,
    HVAC_MODE_FAN_ONLY,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    PRESET_AWAY,
    PRESET_NONE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_NAME,
    CONF_PAYLOAD_OFF,
    CONF_PAYLOAD_ON,
    CONF_TEMPERATURE_UNIT,
    CONF_VALUE_TEMPLATE,
    PRECISION_HALVES,
    PRECISION_TENTHS,
    PRECISION_WHOLE,
    STATE_ON,
)
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import (
    MQTT_BASE_PLATFORM_SCHEMA,
    MqttCommandTemplate,
    MqttValueTemplate,
    subscription,
)
from .. import mqtt
from .const import CONF_ENCODING, CONF_QOS, CONF_RETAIN, PAYLOAD_NONE
from .debug_info import log_messages
from .mixins import (
    MQTT_ENTITY_COMMON_SCHEMA,
    MqttEntity,
    async_setup_entry_helper,
    async_setup_platform_helper,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "MQTT HVAC"

CONF_ACTION_TEMPLATE = "action_template"
CONF_ACTION_TOPIC = "action_topic"
CONF_AUX_COMMAND_TOPIC = "aux_command_topic"
CONF_AUX_STATE_TEMPLATE = "aux_state_template"
CONF_AUX_STATE_TOPIC = "aux_state_topic"
# AWAY and HOLD mode topics and templates are deprecated, support will be removed with release 2022.9
CONF_AWAY_MODE_COMMAND_TOPIC = "away_mode_command_topic"
CONF_AWAY_MODE_STATE_TEMPLATE = "away_mode_state_template"
CONF_AWAY_MODE_STATE_TOPIC = "away_mode_state_topic"
CONF_CURRENT_TEMP_TEMPLATE = "current_temperature_template"
CONF_CURRENT_TEMP_TOPIC = "current_temperature_topic"
CONF_FAN_MODE_COMMAND_TEMPLATE = "fan_mode_command_template"
CONF_FAN_MODE_COMMAND_TOPIC = "fan_mode_command_topic"
CONF_FAN_MODE_LIST = "fan_modes"
CONF_FAN_MODE_STATE_TEMPLATE = "fan_mode_state_template"
CONF_FAN_MODE_STATE_TOPIC = "fan_mode_state_topic"
# AWAY and HOLD mode topics and templates are deprecated, support will be removed with release 2022.9
CONF_HOLD_COMMAND_TEMPLATE = "hold_command_template"
CONF_HOLD_COMMAND_TOPIC = "hold_command_topic"
CONF_HOLD_STATE_TEMPLATE = "hold_state_template"
CONF_HOLD_STATE_TOPIC = "hold_state_topic"
CONF_HOLD_LIST = "hold_modes"
CONF_MODE_COMMAND_TEMPLATE = "mode_command_template"
CONF_MODE_COMMAND_TOPIC = "mode_command_topic"
CONF_MODE_LIST = "modes"
CONF_MODE_STATE_TEMPLATE = "mode_state_template"
CONF_MODE_STATE_TOPIC = "mode_state_topic"
CONF_POWER_COMMAND_TOPIC = "power_command_topic"
CONF_POWER_STATE_TEMPLATE = "power_state_template"
CONF_POWER_STATE_TOPIC = "power_state_topic"
CONF_PRECISION = "precision"
CONF_PRESET_MODE_STATE_TOPIC = "preset_mode_state_topic"
CONF_PRESET_MODE_COMMAND_TOPIC = "preset_mode_command_topic"
CONF_PRESET_MODE_VALUE_TEMPLATE = "preset_mode_value_template"
CONF_PRESET_MODE_COMMAND_TEMPLATE = "preset_mode_command_template"
CONF_PRESET_MODES_LIST = "preset_modes"
# CONF_SEND_IF_OFF is deprecated, support will be removed with release 2022.9
CONF_SEND_IF_OFF = "send_if_off"
CONF_SWING_MODE_COMMAND_TEMPLATE = "swing_mode_command_template"
CONF_SWING_MODE_COMMAND_TOPIC = "swing_mode_command_topic"
CONF_SWING_MODE_LIST = "swing_modes"
CONF_SWING_MODE_STATE_TEMPLATE = "swing_mode_state_template"
CONF_SWING_MODE_STATE_TOPIC = "swing_mode_state_topic"
CONF_TEMP_COMMAND_TEMPLATE = "temperature_command_template"
CONF_TEMP_COMMAND_TOPIC = "temperature_command_topic"
CONF_TEMP_HIGH_COMMAND_TEMPLATE = "temperature_high_command_template"
CONF_TEMP_HIGH_COMMAND_TOPIC = "temperature_high_command_topic"
CONF_TEMP_HIGH_STATE_TEMPLATE = "temperature_high_state_template"
CONF_TEMP_HIGH_STATE_TOPIC = "temperature_high_state_topic"
CONF_TEMP_LOW_COMMAND_TEMPLATE = "temperature_low_command_template"
CONF_TEMP_LOW_COMMAND_TOPIC = "temperature_low_command_topic"
CONF_TEMP_LOW_STATE_TEMPLATE = "temperature_low_state_template"
CONF_TEMP_LOW_STATE_TOPIC = "temperature_low_state_topic"
CONF_TEMP_STATE_TEMPLATE = "temperature_state_template"
CONF_TEMP_STATE_TOPIC = "temperature_state_topic"
CONF_TEMP_INITIAL = "initial"
CONF_TEMP_MAX = "max_temp"
CONF_TEMP_MIN = "min_temp"
CONF_TEMP_STEP = "temp_step"

MQTT_CLIMATE_ATTRIBUTES_BLOCKED = frozenset(
    {
        climate.ATTR_AUX_HEAT,
        climate.ATTR_CURRENT_HUMIDITY,
        climate.ATTR_CURRENT_TEMPERATURE,
        climate.ATTR_FAN_MODE,
        climate.ATTR_FAN_MODES,
        climate.ATTR_HUMIDITY,
        climate.ATTR_HVAC_ACTION,
        climate.ATTR_HVAC_MODES,
        climate.ATTR_MAX_HUMIDITY,
        climate.ATTR_MAX_TEMP,
        climate.ATTR_MIN_HUMIDITY,
        climate.ATTR_MIN_TEMP,
        climate.ATTR_PRESET_MODE,
        climate.ATTR_PRESET_MODES,
        climate.ATTR_SWING_MODE,
        climate.ATTR_SWING_MODES,
        climate.ATTR_TARGET_TEMP_HIGH,
        climate.ATTR_TARGET_TEMP_LOW,
        climate.ATTR_TARGET_TEMP_STEP,
        climate.ATTR_TEMPERATURE,
    }
)

VALUE_TEMPLATE_KEYS = (
    CONF_AUX_STATE_TEMPLATE,
    # AWAY and HOLD mode topics and templates are deprecated, support will be removed with release 2022.9
    CONF_AWAY_MODE_STATE_TEMPLATE,
    CONF_CURRENT_TEMP_TEMPLATE,
    CONF_FAN_MODE_STATE_TEMPLATE,
    # AWAY and HOLD mode topics and templates are deprecated, support will be removed with release 2022.9
    CONF_HOLD_STATE_TEMPLATE,
    CONF_MODE_STATE_TEMPLATE,
    CONF_POWER_STATE_TEMPLATE,
    CONF_ACTION_TEMPLATE,
    CONF_PRESET_MODE_VALUE_TEMPLATE,
    CONF_SWING_MODE_STATE_TEMPLATE,
    CONF_TEMP_HIGH_STATE_TEMPLATE,
    CONF_TEMP_LOW_STATE_TEMPLATE,
    CONF_TEMP_STATE_TEMPLATE,
)

COMMAND_TEMPLATE_KEYS = {
    CONF_FAN_MODE_COMMAND_TEMPLATE,
    # AWAY and HOLD mode topics and templates are deprecated, support will be removed with release 2022.9
    CONF_HOLD_COMMAND_TEMPLATE,
    CONF_MODE_COMMAND_TEMPLATE,
    CONF_PRESET_MODE_COMMAND_TEMPLATE,
    CONF_SWING_MODE_COMMAND_TEMPLATE,
    CONF_TEMP_COMMAND_TEMPLATE,
    CONF_TEMP_HIGH_COMMAND_TEMPLATE,
    CONF_TEMP_LOW_COMMAND_TEMPLATE,
}

# AWAY and HOLD mode topics and templates are deprecated, support will be removed with release 2022.9
DEPRECATED_INVALID = [
    CONF_AWAY_MODE_COMMAND_TOPIC,
    CONF_AWAY_MODE_STATE_TEMPLATE,
    CONF_AWAY_MODE_STATE_TOPIC,
    CONF_HOLD_COMMAND_TEMPLATE,
    CONF_HOLD_COMMAND_TOPIC,
    CONF_HOLD_STATE_TEMPLATE,
    CONF_HOLD_STATE_TOPIC,
    CONF_HOLD_LIST,
]


TOPIC_KEYS = (
    CONF_ACTION_TOPIC,
    CONF_AUX_COMMAND_TOPIC,
    CONF_AUX_STATE_TOPIC,
    # AWAY and HOLD mode topics and templates are deprecated, support will be removed with release 2022.9
    CONF_AWAY_MODE_COMMAND_TOPIC,
    CONF_AWAY_MODE_STATE_TOPIC,
    CONF_CURRENT_TEMP_TOPIC,
    CONF_FAN_MODE_COMMAND_TOPIC,
    CONF_FAN_MODE_STATE_TOPIC,
    # AWAY and HOLD mode topics and templates are deprecated, support will be removed with release 2022.9
    CONF_HOLD_COMMAND_TOPIC,
    CONF_HOLD_STATE_TOPIC,
    CONF_MODE_COMMAND_TOPIC,
    CONF_MODE_STATE_TOPIC,
    CONF_POWER_COMMAND_TOPIC,
    CONF_POWER_STATE_TOPIC,
    CONF_PRESET_MODE_COMMAND_TOPIC,
    CONF_PRESET_MODE_STATE_TOPIC,
    CONF_SWING_MODE_COMMAND_TOPIC,
    CONF_SWING_MODE_STATE_TOPIC,
    CONF_TEMP_COMMAND_TOPIC,
    CONF_TEMP_HIGH_COMMAND_TOPIC,
    CONF_TEMP_HIGH_STATE_TOPIC,
    CONF_TEMP_LOW_COMMAND_TOPIC,
    CONF_TEMP_LOW_STATE_TOPIC,
    CONF_TEMP_STATE_TOPIC,
)


def valid_preset_mode_configuration(config):
    """Validate that the preset mode reset payload is not one of the preset modes."""
    if PRESET_NONE in config.get(CONF_PRESET_MODES_LIST):
        raise ValueError("preset_modes must not include preset mode 'none'")
    if config.get(CONF_PRESET_MODE_COMMAND_TOPIC):
        for config_parameter in DEPRECATED_INVALID:
            if config.get(config_parameter):
                raise vol.MultipleInvalid(
                    "preset_modes cannot be used with deprecated away or hold mode config options"
                )
    return config


SCHEMA_BASE = CLIMATE_PLATFORM_SCHEMA.extend(MQTT_BASE_PLATFORM_SCHEMA.schema)
_PLATFORM_SCHEMA_BASE = SCHEMA_BASE.extend(
    {
        vol.Optional(CONF_AUX_COMMAND_TOPIC): mqtt.valid_publish_topic,
        vol.Optional(CONF_AUX_STATE_TEMPLATE): cv.template,
        vol.Optional(CONF_AUX_STATE_TOPIC): mqtt.valid_subscribe_topic,
        # AWAY and HOLD mode topics and templates are deprecated, support will be removed with release 2022.9
        vol.Optional(CONF_AWAY_MODE_COMMAND_TOPIC): mqtt.valid_publish_topic,
        vol.Optional(CONF_AWAY_MODE_STATE_TEMPLATE): cv.template,
        vol.Optional(CONF_AWAY_MODE_STATE_TOPIC): mqtt.valid_subscribe_topic,
        vol.Optional(CONF_CURRENT_TEMP_TEMPLATE): cv.template,
        vol.Optional(CONF_CURRENT_TEMP_TOPIC): mqtt.valid_subscribe_topic,
        vol.Optional(CONF_FAN_MODE_COMMAND_TEMPLATE): cv.template,
        vol.Optional(CONF_FAN_MODE_COMMAND_TOPIC): mqtt.valid_publish_topic,
        vol.Optional(
            CONF_FAN_MODE_LIST,
            default=[FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH],
        ): cv.ensure_list,
        vol.Optional(CONF_FAN_MODE_STATE_TEMPLATE): cv.template,
        vol.Optional(CONF_FAN_MODE_STATE_TOPIC): mqtt.valid_subscribe_topic,
        # AWAY and HOLD mode topics and templates are deprecated, support will be removed with release 2022.9
        vol.Optional(CONF_HOLD_COMMAND_TEMPLATE): cv.template,
        vol.Optional(CONF_HOLD_COMMAND_TOPIC): mqtt.valid_publish_topic,
        vol.Optional(CONF_HOLD_STATE_TEMPLATE): cv.template,
        vol.Optional(CONF_HOLD_STATE_TOPIC): mqtt.valid_subscribe_topic,
        vol.Optional(CONF_HOLD_LIST): cv.ensure_list,
        vol.Optional(CONF_MODE_COMMAND_TEMPLATE): cv.template,
        vol.Optional(CONF_MODE_COMMAND_TOPIC): mqtt.valid_publish_topic,
        vol.Optional(
            CONF_MODE_LIST,
            default=[
                HVAC_MODE_AUTO,
                HVAC_MODE_OFF,
                HVAC_MODE_COOL,
                HVAC_MODE_HEAT,
                HVAC_MODE_DRY,
                HVAC_MODE_FAN_ONLY,
            ],
        ): cv.ensure_list,
        vol.Optional(CONF_MODE_STATE_TEMPLATE): cv.template,
        vol.Optional(CONF_MODE_STATE_TOPIC): mqtt.valid_subscribe_topic,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_PAYLOAD_ON, default="ON"): cv.string,
        vol.Optional(CONF_PAYLOAD_OFF, default="OFF"): cv.string,
        vol.Optional(CONF_POWER_COMMAND_TOPIC): mqtt.valid_publish_topic,
        vol.Optional(CONF_POWER_STATE_TEMPLATE): cv.template,
        vol.Optional(CONF_POWER_STATE_TOPIC): mqtt.valid_subscribe_topic,
        vol.Optional(CONF_PRECISION): vol.In(
            [PRECISION_TENTHS, PRECISION_HALVES, PRECISION_WHOLE]
        ),
        vol.Optional(CONF_RETAIN, default=mqtt.DEFAULT_RETAIN): cv.boolean,
        # CONF_SEND_IF_OFF is deprecated, support will be removed with release 2022.9
        vol.Optional(CONF_SEND_IF_OFF): cv.boolean,
        vol.Optional(CONF_ACTION_TEMPLATE): cv.template,
        vol.Optional(CONF_ACTION_TOPIC): mqtt.valid_subscribe_topic,
        # CONF_PRESET_MODE_COMMAND_TOPIC and CONF_PRESET_MODES_LIST must be used together
        vol.Inclusive(
            CONF_PRESET_MODE_COMMAND_TOPIC, "preset_modes"
        ): mqtt.valid_publish_topic,
        vol.Inclusive(
            CONF_PRESET_MODES_LIST, "preset_modes", default=[]
        ): cv.ensure_list,
        vol.Optional(CONF_PRESET_MODE_COMMAND_TEMPLATE): cv.template,
        vol.Optional(CONF_PRESET_MODE_STATE_TOPIC): mqtt.valid_subscribe_topic,
        vol.Optional(CONF_PRESET_MODE_VALUE_TEMPLATE): cv.template,
        vol.Optional(CONF_SWING_MODE_COMMAND_TEMPLATE): cv.template,
        vol.Optional(CONF_SWING_MODE_COMMAND_TOPIC): mqtt.valid_publish_topic,
        vol.Optional(
            CONF_SWING_MODE_LIST, default=[STATE_ON, HVAC_MODE_OFF]
        ): cv.ensure_list,
        vol.Optional(CONF_SWING_MODE_STATE_TEMPLATE): cv.template,
        vol.Optional(CONF_SWING_MODE_STATE_TOPIC): mqtt.valid_subscribe_topic,
        vol.Optional(CONF_TEMP_INITIAL, default=21): cv.positive_int,
        vol.Optional(CONF_TEMP_MIN, default=DEFAULT_MIN_TEMP): vol.Coerce(float),
        vol.Optional(CONF_TEMP_MAX, default=DEFAULT_MAX_TEMP): vol.Coerce(float),
        vol.Optional(CONF_TEMP_STEP, default=1.0): vol.Coerce(float),
        vol.Optional(CONF_TEMP_COMMAND_TEMPLATE): cv.template,
        vol.Optional(CONF_TEMP_COMMAND_TOPIC): mqtt.valid_publish_topic,
        vol.Optional(CONF_TEMP_HIGH_COMMAND_TEMPLATE): cv.template,
        vol.Optional(CONF_TEMP_HIGH_COMMAND_TOPIC): mqtt.valid_publish_topic,
        vol.Optional(CONF_TEMP_HIGH_STATE_TOPIC): mqtt.valid_subscribe_topic,
        vol.Optional(CONF_TEMP_HIGH_STATE_TEMPLATE): cv.template,
        vol.Optional(CONF_TEMP_LOW_COMMAND_TEMPLATE): cv.template,
        vol.Optional(CONF_TEMP_LOW_COMMAND_TOPIC): mqtt.valid_publish_topic,
        vol.Optional(CONF_TEMP_LOW_STATE_TEMPLATE): cv.template,
        vol.Optional(CONF_TEMP_LOW_STATE_TOPIC): mqtt.valid_subscribe_topic,
        vol.Optional(CONF_TEMP_STATE_TEMPLATE): cv.template,
        vol.Optional(CONF_TEMP_STATE_TOPIC): mqtt.valid_subscribe_topic,
        vol.Optional(CONF_TEMPERATURE_UNIT): cv.temperature_unit,
        vol.Optional(CONF_VALUE_TEMPLATE): cv.template,
    }
).extend(MQTT_ENTITY_COMMON_SCHEMA.schema)

PLATFORM_SCHEMA = vol.All(
    _PLATFORM_SCHEMA_BASE,
    # CONF_SEND_IF_OFF is deprecated, support will be removed with release 2022.9
    cv.deprecated(CONF_SEND_IF_OFF),
    # AWAY and HOLD mode topics and templates are deprecated, support will be removed with release 2022.9
    cv.deprecated(CONF_AWAY_MODE_COMMAND_TOPIC),
    cv.deprecated(CONF_AWAY_MODE_STATE_TEMPLATE),
    cv.deprecated(CONF_AWAY_MODE_STATE_TOPIC),
    cv.deprecated(CONF_HOLD_COMMAND_TEMPLATE),
    cv.deprecated(CONF_HOLD_COMMAND_TOPIC),
    cv.deprecated(CONF_HOLD_STATE_TEMPLATE),
    cv.deprecated(CONF_HOLD_STATE_TOPIC),
    cv.deprecated(CONF_HOLD_LIST),
    valid_preset_mode_configuration,
)

_DISCOVERY_SCHEMA_BASE = _PLATFORM_SCHEMA_BASE.extend({}, extra=vol.REMOVE_EXTRA)

DISCOVERY_SCHEMA = vol.All(
    _DISCOVERY_SCHEMA_BASE,
    # CONF_SEND_IF_OFF is deprecated, support will be removed with release 2022.9
    cv.deprecated(CONF_SEND_IF_OFF),
    # AWAY and HOLD mode topics and templates are deprecated, support will be removed with release 2022.9
    cv.deprecated(CONF_AWAY_MODE_COMMAND_TOPIC),
    cv.deprecated(CONF_AWAY_MODE_STATE_TEMPLATE),
    cv.deprecated(CONF_AWAY_MODE_STATE_TOPIC),
    cv.deprecated(CONF_HOLD_COMMAND_TEMPLATE),
    cv.deprecated(CONF_HOLD_COMMAND_TOPIC),
    cv.deprecated(CONF_HOLD_STATE_TEMPLATE),
    cv.deprecated(CONF_HOLD_STATE_TOPIC),
    cv.deprecated(CONF_HOLD_LIST),
    valid_preset_mode_configuration,
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up MQTT climate device through configuration.yaml."""
    await async_setup_platform_helper(
        hass, climate.DOMAIN, config, async_add_entities, _async_setup_entity
    )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MQTT climate device dynamically through MQTT discovery."""
    setup = functools.partial(
        _async_setup_entity, hass, async_add_entities, config_entry=config_entry
    )
    await async_setup_entry_helper(hass, climate.DOMAIN, setup, DISCOVERY_SCHEMA)


async def _async_setup_entity(
    hass, async_add_entities, config, config_entry=None, discovery_data=None
):
    """Set up the MQTT climate devices."""
    async_add_entities([MqttClimate(hass, config, config_entry, discovery_data)])


class MqttClimate(MqttEntity, ClimateEntity):
    """Representation of an MQTT climate device."""

    _entity_id_format = climate.ENTITY_ID_FORMAT
    _attributes_extra_blocked = MQTT_CLIMATE_ATTRIBUTES_BLOCKED

    def __init__(self, hass, config, config_entry, discovery_data):
        """Initialize the climate device."""
        self._action = None
        self._aux = False
        self._away = False
        self._current_fan_mode = None
        self._current_operation = None
        self._current_swing_mode = None
        self._current_temp = None
        self._hold = None
        self._preset_mode = None
        self._target_temp = None
        self._target_temp_high = None
        self._target_temp_low = None
        self._topic = None
        self._value_templates = None
        self._command_templates = None
        self._feature_preset_mode = False
        self._optimistic_preset_mode = None

        # CONF_SEND_IF_OFF is deprecated, support will be removed with release 2022.9
        self._send_if_off = True
        # AWAY and HOLD mode topics and templates are deprecated,
        # support will be removed with release 2022.9
        self._hold_list = []

        MqttEntity.__init__(self, hass, config, config_entry, discovery_data)

    @staticmethod
    def config_schema():
        """Return the config schema."""
        return DISCOVERY_SCHEMA

    def _setup_from_config(self, config):
        """(Re)Setup the entity."""
        self._topic = {key: config.get(key) for key in TOPIC_KEYS}

        # set to None in non-optimistic mode
        self._target_temp = (
            self._current_fan_mode
        ) = self._current_operation = self._current_swing_mode = None
        self._target_temp_low = None
        self._target_temp_high = None

        if self._topic[CONF_TEMP_STATE_TOPIC] is None:
            self._target_temp = config[CONF_TEMP_INITIAL]
        if self._topic[CONF_TEMP_LOW_STATE_TOPIC] is None:
            self._target_temp_low = config[CONF_TEMP_INITIAL]
        if self._topic[CONF_TEMP_HIGH_STATE_TOPIC] is None:
            self._target_temp_high = config[CONF_TEMP_INITIAL]

        if self._topic[CONF_FAN_MODE_STATE_TOPIC] is None:
            self._current_fan_mode = FAN_LOW
        if self._topic[CONF_SWING_MODE_STATE_TOPIC] is None:
            self._current_swing_mode = HVAC_MODE_OFF
        if self._topic[CONF_MODE_STATE_TOPIC] is None:
            self._current_operation = HVAC_MODE_OFF
        self._feature_preset_mode = CONF_PRESET_MODE_COMMAND_TOPIC in config
        if self._feature_preset_mode:
            self._preset_modes = config[CONF_PRESET_MODES_LIST]
        else:
            self._preset_modes = []
        self._optimistic_preset_mode = CONF_PRESET_MODE_STATE_TOPIC not in config
        self._action = None
        # AWAY and HOLD mode topics and templates are deprecated, support will be removed with release 2022.9
        self._away = False
        self._hold = None
        self._aux = False

        value_templates = {}
        for key in VALUE_TEMPLATE_KEYS:
            value_templates[key] = None
        if CONF_VALUE_TEMPLATE in config:
            value_templates = {
                key: config.get(CONF_VALUE_TEMPLATE) for key in VALUE_TEMPLATE_KEYS
            }
        for key in VALUE_TEMPLATE_KEYS & config.keys():
            value_templates[key] = config[key]
        self._value_templates = {
            key: MqttValueTemplate(
                template,
                entity=self,
            ).async_render_with_possible_json_value
            for key, template in value_templates.items()
        }

        command_templates = {}
        for key in COMMAND_TEMPLATE_KEYS:
            command_templates[key] = MqttCommandTemplate(
                config.get(key), entity=self
            ).async_render

        self._command_templates = command_templates

        # CONF_SEND_IF_OFF is deprecated, support will be removed with release 2022.9
        if CONF_SEND_IF_OFF in config:
            self._send_if_off = config[CONF_SEND_IF_OFF]

        # AWAY and HOLD mode topics and templates are deprecated,
        # support will be removed with release 2022.9
        if CONF_HOLD_LIST in config:
            self._hold_list = config[CONF_HOLD_LIST]

    def _prepare_subscribe_topics(self):  # noqa: C901
        """(Re)Subscribe to topics."""
        topics = {}
        qos = self._config[CONF_QOS]

        def add_subscription(topics, topic, msg_callback):
            if self._topic[topic] is not None:
                topics[topic] = {
                    "topic": self._topic[topic],
                    "msg_callback": msg_callback,
                    "qos": qos,
                    "encoding": self._config[CONF_ENCODING] or None,
                }

        def render_template(msg, template_name):
            template = self._value_templates[template_name]
            return template(msg.payload)

        @callback
        @log_messages(self.hass, self.entity_id)
        def handle_action_received(msg):
            """Handle receiving action via MQTT."""
            payload = render_template(msg, CONF_ACTION_TEMPLATE)
            if payload in CURRENT_HVAC_ACTIONS:
                self._action = payload
                self.async_write_ha_state()
            elif not payload or payload == PAYLOAD_NONE:
                _LOGGER.debug(
                    "Invalid %s action: %s, ignoring",
                    CURRENT_HVAC_ACTIONS,
                    payload,
                )
            else:
                _LOGGER.warning(
                    "Invalid %s action: %s",
                    CURRENT_HVAC_ACTIONS,
                    payload,
                )

        add_subscription(topics, CONF_ACTION_TOPIC, handle_action_received)

        @callback
        def handle_temperature_received(msg, template_name, attr):
            """Handle temperature coming via MQTT."""
            payload = render_template(msg, template_name)

            try:
                setattr(self, attr, float(payload))
                self.async_write_ha_state()
            except ValueError:
                _LOGGER.error("Could not parse temperature from %s", payload)

        @callback
        @log_messages(self.hass, self.entity_id)
        def handle_current_temperature_received(msg):
            """Handle current temperature coming via MQTT."""
            handle_temperature_received(
                msg, CONF_CURRENT_TEMP_TEMPLATE, "_current_temp"
            )

        add_subscription(
            topics, CONF_CURRENT_TEMP_TOPIC, handle_current_temperature_received
        )

        @callback
        @log_messages(self.hass, self.entity_id)
        def handle_target_temperature_received(msg):
            """Handle target temperature coming via MQTT."""
            handle_temperature_received(msg, CONF_TEMP_STATE_TEMPLATE, "_target_temp")

        add_subscription(
            topics, CONF_TEMP_STATE_TOPIC, handle_target_temperature_received
        )

        @callback
        @log_messages(self.hass, self.entity_id)
        def handle_temperature_low_received(msg):
            """Handle target temperature low coming via MQTT."""
            handle_temperature_received(
                msg, CONF_TEMP_LOW_STATE_TEMPLATE, "_target_temp_low"
            )

        add_subscription(
            topics, CONF_TEMP_LOW_STATE_TOPIC, handle_temperature_low_received
        )

        @callback
        @log_messages(self.hass, self.entity_id)
        def handle_temperature_high_received(msg):
            """Handle target temperature high coming via MQTT."""
            handle_temperature_received(
                msg, CONF_TEMP_HIGH_STATE_TEMPLATE, "_target_temp_high"
            )

        add_subscription(
            topics, CONF_TEMP_HIGH_STATE_TOPIC, handle_temperature_high_received
        )

        @callback
        def handle_mode_received(msg, template_name, attr, mode_list):
            """Handle receiving listed mode via MQTT."""
            payload = render_template(msg, template_name)

            if payload not in self._config[mode_list]:
                _LOGGER.error("Invalid %s mode: %s", mode_list, payload)
            else:
                setattr(self, attr, payload)
                self.async_write_ha_state()

        @callback
        @log_messages(self.hass, self.entity_id)
        def handle_current_mode_received(msg):
            """Handle receiving mode via MQTT."""
            handle_mode_received(
                msg, CONF_MODE_STATE_TEMPLATE, "_current_operation", CONF_MODE_LIST
            )

        add_subscription(topics, CONF_MODE_STATE_TOPIC, handle_current_mode_received)

        @callback
        @log_messages(self.hass, self.entity_id)
        def handle_fan_mode_received(msg):
            """Handle receiving fan mode via MQTT."""
            handle_mode_received(
                msg,
                CONF_FAN_MODE_STATE_TEMPLATE,
                "_current_fan_mode",
                CONF_FAN_MODE_LIST,
            )

        add_subscription(topics, CONF_FAN_MODE_STATE_TOPIC, handle_fan_mode_received)

        @callback
        @log_messages(self.hass, self.entity_id)
        def handle_swing_mode_received(msg):
            """Handle receiving swing mode via MQTT."""
            handle_mode_received(
                msg,
                CONF_SWING_MODE_STATE_TEMPLATE,
                "_current_swing_mode",
                CONF_SWING_MODE_LIST,
            )

        add_subscription(
            topics, CONF_SWING_MODE_STATE_TOPIC, handle_swing_mode_received
        )

        @callback
        def handle_onoff_mode_received(msg, template_name, attr):
            """Handle receiving on/off mode via MQTT."""
            payload = render_template(msg, template_name)
            payload_on = self._config[CONF_PAYLOAD_ON]
            payload_off = self._config[CONF_PAYLOAD_OFF]

            if payload == "True":
                payload = payload_on
            elif payload == "False":
                payload = payload_off

            if payload == payload_on:
                setattr(self, attr, True)
            elif payload == payload_off:
                setattr(self, attr, False)
            else:
                _LOGGER.error("Invalid %s mode: %s", attr, payload)

            self.async_write_ha_state()

        # AWAY and HOLD mode topics and templates are deprecated, support will be removed with release 2022.9
        @callback
        @log_messages(self.hass, self.entity_id)
        def handle_away_mode_received(msg):
            """Handle receiving away mode via MQTT."""
            handle_onoff_mode_received(msg, CONF_AWAY_MODE_STATE_TEMPLATE, "_away")

        add_subscription(topics, CONF_AWAY_MODE_STATE_TOPIC, handle_away_mode_received)

        @callback
        @log_messages(self.hass, self.entity_id)
        def handle_aux_mode_received(msg):
            """Handle receiving aux mode via MQTT."""
            handle_onoff_mode_received(msg, CONF_AUX_STATE_TEMPLATE, "_aux")

        add_subscription(topics, CONF_AUX_STATE_TOPIC, handle_aux_mode_received)

        # AWAY and HOLD mode topics and templates are deprecated, support will be removed with release 2022.9
        @callback
        @log_messages(self.hass, self.entity_id)
        def handle_hold_mode_received(msg):
            """Handle receiving hold mode via MQTT."""
            payload = render_template(msg, CONF_HOLD_STATE_TEMPLATE)

            if payload == "off":
                payload = None

            self._hold = payload
            self._preset_mode = None
            self.async_write_ha_state()

        add_subscription(topics, CONF_HOLD_STATE_TOPIC, handle_hold_mode_received)

        @callback
        @log_messages(self.hass, self.entity_id)
        def handle_preset_mode_received(msg):
            """Handle receiving preset mode via MQTT."""
            preset_mode = render_template(msg, CONF_PRESET_MODE_VALUE_TEMPLATE)
            if preset_mode in [PRESET_NONE, PAYLOAD_NONE]:
                self._preset_mode = None
                self.async_write_ha_state()
                return
            if not preset_mode:
                _LOGGER.debug("Ignoring empty preset_mode from '%s'", msg.topic)
                return
            if preset_mode not in self._preset_modes:
                _LOGGER.warning(
                    "'%s' received on topic %s. '%s' is not a valid preset mode",
                    msg.payload,
                    msg.topic,
                    preset_mode,
                )
            else:
                self._preset_mode = preset_mode
                self.async_write_ha_state()

        add_subscription(
            topics, CONF_PRESET_MODE_STATE_TOPIC, handle_preset_mode_received
        )

        self._sub_state = subscription.async_prepare_subscribe_topics(
            self.hass, self._sub_state, topics
        )

    async def _subscribe_topics(self):
        """(Re)Subscribe to topics."""
        await subscription.async_subscribe_topics(self.hass, self._sub_state)

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        if self._config.get(CONF_TEMPERATURE_UNIT):
            return self._config.get(CONF_TEMPERATURE_UNIT)
        return self.hass.config.units.temperature_unit

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._current_temp

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temp

    @property
    def target_temperature_low(self):
        """Return the low target temperature we try to reach."""
        return self._target_temp_low

    @property
    def target_temperature_high(self):
        """Return the high target temperature we try to reach."""
        return self._target_temp_high

    @property
    def hvac_action(self):
        """Return the current running hvac operation if supported."""
        return self._action

    @property
    def hvac_mode(self):
        """Return current operation ie. heat, cool, idle."""
        return self._current_operation

    @property
    def hvac_modes(self):
        """Return the list of available operation modes."""
        return self._config[CONF_MODE_LIST]

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return self._config[CONF_TEMP_STEP]

    @property
    def preset_mode(self) -> str | None:
        """Return preset mode."""
        if self._feature_preset_mode and self._preset_mode is not None:
            return self._preset_mode
        # AWAY and HOLD mode topics and templates are deprecated, support will be removed with release 2022.9
        if self._hold:
            return self._hold
        if self._away:
            return PRESET_AWAY
        return PRESET_NONE

    @property
    def preset_modes(self) -> list:
        """Return preset modes."""
        presets = []
        presets.extend(self._preset_modes)

        # AWAY and HOLD mode topics and templates are deprecated, support will be removed with release 2022.9
        if (self._topic[CONF_AWAY_MODE_STATE_TOPIC] is not None) or (
            self._topic[CONF_AWAY_MODE_COMMAND_TOPIC] is not None
        ):
            presets.append(PRESET_AWAY)

        # AWAY and HOLD mode topics and templates are deprecated,
        # support will be removed with release 2022.9
        presets.extend(self._hold_list)

        if presets:
            presets.insert(0, PRESET_NONE)

        return presets

    @property
    def is_aux_heat(self):
        """Return true if away mode is on."""
        return self._aux

    @property
    def fan_mode(self):
        """Return the fan setting."""
        return self._current_fan_mode

    @property
    def fan_modes(self):
        """Return the list of available fan modes."""
        return self._config[CONF_FAN_MODE_LIST]

    async def _publish(self, topic, payload):
        if self._topic[topic] is not None:
            await self.async_publish(
                self._topic[topic],
                payload,
                self._config[CONF_QOS],
                self._config[CONF_RETAIN],
                self._config[CONF_ENCODING],
            )

    async def _set_temperature(
        self, temp, cmnd_topic, cmnd_template, state_topic, attr
    ):
        if temp is not None:
            if self._topic[state_topic] is None:
                # optimistic mode
                setattr(self, attr, temp)

            # CONF_SEND_IF_OFF is deprecated, support will be removed with release 2022.9
            if self._send_if_off or self._current_operation != HVAC_MODE_OFF:
                payload = self._command_templates[cmnd_template](temp)
                await self._publish(cmnd_topic, payload)

    async def async_set_temperature(self, **kwargs):
        """Set new target temperatures."""
        if kwargs.get(ATTR_HVAC_MODE) is not None:
            operation_mode = kwargs.get(ATTR_HVAC_MODE)
            await self.async_set_hvac_mode(operation_mode)

        await self._set_temperature(
            kwargs.get(ATTR_TEMPERATURE),
            CONF_TEMP_COMMAND_TOPIC,
            CONF_TEMP_COMMAND_TEMPLATE,
            CONF_TEMP_STATE_TOPIC,
            "_target_temp",
        )

        await self._set_temperature(
            kwargs.get(ATTR_TARGET_TEMP_LOW),
            CONF_TEMP_LOW_COMMAND_TOPIC,
            CONF_TEMP_LOW_COMMAND_TEMPLATE,
            CONF_TEMP_LOW_STATE_TOPIC,
            "_target_temp_low",
        )

        await self._set_temperature(
            kwargs.get(ATTR_TARGET_TEMP_HIGH),
            CONF_TEMP_HIGH_COMMAND_TOPIC,
            CONF_TEMP_HIGH_COMMAND_TEMPLATE,
            CONF_TEMP_HIGH_STATE_TOPIC,
            "_target_temp_high",
        )

        # Always optimistic?
        self.async_write_ha_state()

    async def async_set_swing_mode(self, swing_mode):
        """Set new swing mode."""
        # CONF_SEND_IF_OFF is deprecated, support will be removed with release 2022.9
        if self._send_if_off or self._current_operation != HVAC_MODE_OFF:
            payload = self._command_templates[CONF_SWING_MODE_COMMAND_TEMPLATE](
                swing_mode
            )
            await self._publish(CONF_SWING_MODE_COMMAND_TOPIC, payload)

        if self._topic[CONF_SWING_MODE_STATE_TOPIC] is None:
            self._current_swing_mode = swing_mode
            self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode):
        """Set new target temperature."""
        # CONF_SEND_IF_OFF is deprecated, support will be removed with release 2022.9
        if self._send_if_off or self._current_operation != HVAC_MODE_OFF:
            payload = self._command_templates[CONF_FAN_MODE_COMMAND_TEMPLATE](fan_mode)
            await self._publish(CONF_FAN_MODE_COMMAND_TOPIC, payload)

        if self._topic[CONF_FAN_MODE_STATE_TOPIC] is None:
            self._current_fan_mode = fan_mode
            self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode) -> None:
        """Set new operation mode."""
        if hvac_mode == HVAC_MODE_OFF:
            await self._publish(
                CONF_POWER_COMMAND_TOPIC, self._config[CONF_PAYLOAD_OFF]
            )
        else:
            await self._publish(CONF_POWER_COMMAND_TOPIC, self._config[CONF_PAYLOAD_ON])

        payload = self._command_templates[CONF_MODE_COMMAND_TEMPLATE](hvac_mode)
        await self._publish(CONF_MODE_COMMAND_TOPIC, payload)

        if self._topic[CONF_MODE_STATE_TOPIC] is None:
            self._current_operation = hvac_mode
            self.async_write_ha_state()

    @property
    def swing_mode(self):
        """Return the swing setting."""
        return self._current_swing_mode

    @property
    def swing_modes(self):
        """List of available swing modes."""
        return self._config[CONF_SWING_MODE_LIST]

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set a preset mode."""
        if self._feature_preset_mode:
            if preset_mode not in self.preset_modes and preset_mode is not PRESET_NONE:
                _LOGGER.warning("'%s' is not a valid preset mode", preset_mode)
                return
            mqtt_payload = self._command_templates[CONF_PRESET_MODE_COMMAND_TEMPLATE](
                preset_mode
            )
            await self._publish(
                CONF_PRESET_MODE_COMMAND_TOPIC,
                mqtt_payload,
            )

            if self._optimistic_preset_mode:
                self._preset_mode = preset_mode if preset_mode != PRESET_NONE else None
                self.async_write_ha_state()

            return

        # Update hold or away mode: Track if we should optimistic update the state
        optimistic_update = await self._set_away_mode(preset_mode == PRESET_AWAY)
        hold_mode: str | None = preset_mode
        if preset_mode in [PRESET_NONE, PRESET_AWAY]:
            hold_mode = None
        optimistic_update = await self._set_hold_mode(hold_mode) or optimistic_update

        if optimistic_update:
            self.async_write_ha_state()

    # AWAY and HOLD mode topics and templates are deprecated, support will be removed with release 2022.9
    async def _set_away_mode(self, state):
        """Set away mode.

        Returns if we should optimistically write the state.
        """
        await self._publish(
            CONF_AWAY_MODE_COMMAND_TOPIC,
            self._config[CONF_PAYLOAD_ON] if state else self._config[CONF_PAYLOAD_OFF],
        )

        if self._topic[CONF_AWAY_MODE_STATE_TOPIC] is not None:
            return False

        self._away = state
        return True

    async def _set_hold_mode(self, hold_mode):
        """Set hold mode.

        Returns if we should optimistically write the state.
        """
        payload = self._command_templates[CONF_HOLD_COMMAND_TEMPLATE](
            hold_mode or "off"
        )
        await self._publish(CONF_HOLD_COMMAND_TOPIC, payload)

        if self._topic[CONF_HOLD_STATE_TOPIC] is not None:
            return False

        self._hold = hold_mode
        return True

    async def _set_aux_heat(self, state):
        await self._publish(
            CONF_AUX_COMMAND_TOPIC,
            self._config[CONF_PAYLOAD_ON] if state else self._config[CONF_PAYLOAD_OFF],
        )

        if self._topic[CONF_AUX_STATE_TOPIC] is None:
            self._aux = state
            self.async_write_ha_state()

    async def async_turn_aux_heat_on(self):
        """Turn auxiliary heater on."""
        await self._set_aux_heat(True)

    async def async_turn_aux_heat_off(self):
        """Turn auxiliary heater off."""
        await self._set_aux_heat(False)

    @property
    def supported_features(self):
        """Return the list of supported features."""
        support = 0

        if (self._topic[CONF_TEMP_STATE_TOPIC] is not None) or (
            self._topic[CONF_TEMP_COMMAND_TOPIC] is not None
        ):
            support |= ClimateEntityFeature.TARGET_TEMPERATURE

        if (self._topic[CONF_TEMP_LOW_STATE_TOPIC] is not None) or (
            self._topic[CONF_TEMP_LOW_COMMAND_TOPIC] is not None
        ):
            support |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE

        if (self._topic[CONF_TEMP_HIGH_STATE_TOPIC] is not None) or (
            self._topic[CONF_TEMP_HIGH_COMMAND_TOPIC] is not None
        ):
            support |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE

        if (self._topic[CONF_FAN_MODE_STATE_TOPIC] is not None) or (
            self._topic[CONF_FAN_MODE_COMMAND_TOPIC] is not None
        ):
            support |= ClimateEntityFeature.FAN_MODE

        if (self._topic[CONF_SWING_MODE_STATE_TOPIC] is not None) or (
            self._topic[CONF_SWING_MODE_COMMAND_TOPIC] is not None
        ):
            support |= ClimateEntityFeature.SWING_MODE

        # AWAY and HOLD mode topics and templates are deprecated, support will be removed with release 2022.9
        if (
            self._feature_preset_mode
            or (self._topic[CONF_AWAY_MODE_STATE_TOPIC] is not None)
            or (self._topic[CONF_AWAY_MODE_COMMAND_TOPIC] is not None)
            or (self._topic[CONF_HOLD_STATE_TOPIC] is not None)
            or (self._topic[CONF_HOLD_COMMAND_TOPIC] is not None)
        ):
            support |= ClimateEntityFeature.PRESET_MODE

        if (self._topic[CONF_AUX_STATE_TOPIC] is not None) or (
            self._topic[CONF_AUX_COMMAND_TOPIC] is not None
        ):
            support |= ClimateEntityFeature.AUX_HEAT

        return support

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self._config[CONF_TEMP_MIN]

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self._config[CONF_TEMP_MAX]

    @property
    def precision(self):
        """Return the precision of the system."""
        if self._config.get(CONF_PRECISION) is not None:
            return self._config.get(CONF_PRECISION)
        return super().precision
