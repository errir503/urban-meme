"""Support for tracking MQTT enabled devices."""
import asyncio
import functools

import voluptuous as vol

from homeassistant.components import device_tracker
from homeassistant.components.device_tracker import SOURCE_TYPES
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.const import (
    ATTR_GPS_ACCURACY,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CONF_NAME,
    CONF_VALUE_TEMPLATE,
    STATE_HOME,
    STATE_NOT_HOME,
)
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from .. import MqttValueTemplate, subscription
from ... import mqtt
from ..const import CONF_QOS, CONF_STATE_TOPIC
from ..debug_info import log_messages
from ..mixins import (
    MQTT_ENTITY_COMMON_SCHEMA,
    MqttEntity,
    async_get_platform_config_from_yaml,
    async_setup_entry_helper,
)

CONF_PAYLOAD_HOME = "payload_home"
CONF_PAYLOAD_NOT_HOME = "payload_not_home"
CONF_SOURCE_TYPE = "source_type"

PLATFORM_SCHEMA_MODERN = mqtt.MQTT_RO_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_PAYLOAD_HOME, default=STATE_HOME): cv.string,
        vol.Optional(CONF_PAYLOAD_NOT_HOME, default=STATE_NOT_HOME): cv.string,
        vol.Optional(CONF_SOURCE_TYPE): vol.In(SOURCE_TYPES),
    }
).extend(MQTT_ENTITY_COMMON_SCHEMA.schema)

DISCOVERY_SCHEMA = PLATFORM_SCHEMA_MODERN.extend({}, extra=vol.REMOVE_EXTRA)


async def async_setup_entry_from_discovery(hass, config_entry, async_add_entities):
    """Set up MQTT device tracker configuration.yaml and dynamically through MQTT discovery."""
    # load and initialize platform config from configuration.yaml
    await asyncio.gather(
        *(
            _async_setup_entity(hass, async_add_entities, config, config_entry)
            for config in await async_get_platform_config_from_yaml(
                hass, device_tracker.DOMAIN, PLATFORM_SCHEMA_MODERN
            )
        )
    )
    # setup for discovery
    setup = functools.partial(
        _async_setup_entity, hass, async_add_entities, config_entry=config_entry
    )
    await async_setup_entry_helper(hass, device_tracker.DOMAIN, setup, DISCOVERY_SCHEMA)


async def _async_setup_entity(
    hass, async_add_entities, config, config_entry=None, discovery_data=None
):
    """Set up the MQTT Device Tracker entity."""
    async_add_entities([MqttDeviceTracker(hass, config, config_entry, discovery_data)])


class MqttDeviceTracker(MqttEntity, TrackerEntity):
    """Representation of a device tracker using MQTT."""

    _entity_id_format = device_tracker.ENTITY_ID_FORMAT

    def __init__(self, hass, config, config_entry, discovery_data):
        """Initialize the tracker."""
        self._location_name = None

        MqttEntity.__init__(self, hass, config, config_entry, discovery_data)

    @staticmethod
    def config_schema():
        """Return the config schema."""
        return DISCOVERY_SCHEMA

    def _setup_from_config(self, config):
        """(Re)Setup the entity."""
        self._value_template = MqttValueTemplate(
            self._config.get(CONF_VALUE_TEMPLATE), entity=self
        ).async_render_with_possible_json_value

    def _prepare_subscribe_topics(self):
        """(Re)Subscribe to topics."""

        @callback
        @log_messages(self.hass, self.entity_id)
        def message_received(msg):
            """Handle new MQTT messages."""
            payload = self._value_template(msg.payload)
            if payload == self._config[CONF_PAYLOAD_HOME]:
                self._location_name = STATE_HOME
            elif payload == self._config[CONF_PAYLOAD_NOT_HOME]:
                self._location_name = STATE_NOT_HOME
            else:
                self._location_name = msg.payload

            self.async_write_ha_state()

        self._sub_state = subscription.async_prepare_subscribe_topics(
            self.hass,
            self._sub_state,
            {
                "state_topic": {
                    "topic": self._config[CONF_STATE_TOPIC],
                    "msg_callback": message_received,
                    "qos": self._config[CONF_QOS],
                }
            },
        )

    async def _subscribe_topics(self):
        """(Re)Subscribe to topics."""
        await subscription.async_subscribe_topics(self.hass, self._sub_state)

    @property
    def latitude(self):
        """Return latitude if provided in extra_state_attributes or None."""
        if (
            self.extra_state_attributes is not None
            and ATTR_LATITUDE in self.extra_state_attributes
        ):
            return self.extra_state_attributes[ATTR_LATITUDE]
        return None

    @property
    def location_accuracy(self):
        """Return location accuracy if provided in extra_state_attributes or None."""
        if (
            self.extra_state_attributes is not None
            and ATTR_GPS_ACCURACY in self.extra_state_attributes
        ):
            return self.extra_state_attributes[ATTR_GPS_ACCURACY]
        return None

    @property
    def longitude(self):
        """Return longitude if provided in extra_state_attributes or None."""
        if (
            self.extra_state_attributes is not None
            and ATTR_LONGITUDE in self.extra_state_attributes
        ):
            return self.extra_state_attributes[ATTR_LONGITUDE]
        return None

    @property
    def location_name(self):
        """Return a location name for the current location of the device."""
        return self._location_name

    @property
    def source_type(self):
        """Return the source type, eg gps or router, of the device."""
        return self._config.get(CONF_SOURCE_TYPE)
