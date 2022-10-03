"""Provides tag scanning for MQTT."""
from __future__ import annotations

import functools

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE, CONF_PLATFORM, CONF_VALUE_TEMPLATE
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

from . import subscription
from .config import MQTT_BASE_SCHEMA
from .const import ATTR_DISCOVERY_HASH, CONF_QOS, CONF_TOPIC
from .mixins import (
    MQTT_ENTITY_DEVICE_INFO_SCHEMA,
    MqttDiscoveryDeviceUpdate,
    async_setup_entry_helper,
    send_discovery_done,
    update_device,
)
from .models import MqttValueTemplate, ReceiveMessage
from .subscription import EntitySubscription
from .util import get_mqtt_data, valid_subscribe_topic

LOG_NAME = "Tag"

TAG = "tag"

PLATFORM_SCHEMA = MQTT_BASE_SCHEMA.extend(
    {
        vol.Optional(CONF_DEVICE): MQTT_ENTITY_DEVICE_INFO_SCHEMA,
        vol.Optional(CONF_PLATFORM): "mqtt",
        vol.Required(CONF_TOPIC): valid_subscribe_topic,
        vol.Optional(CONF_VALUE_TEMPLATE): cv.template,
    },
    extra=vol.REMOVE_EXTRA,
)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Set up MQTT device automation dynamically through MQTT discovery."""

    setup = functools.partial(_async_setup_tag, hass, config_entry=config_entry)
    await async_setup_entry_helper(hass, TAG, setup, PLATFORM_SCHEMA)


async def _async_setup_tag(
    hass: HomeAssistant,
    config: ConfigType,
    config_entry: ConfigEntry,
    discovery_data: dict,
) -> None:
    """Set up the MQTT tag scanner."""
    discovery_hash = discovery_data[ATTR_DISCOVERY_HASH]
    discovery_id = discovery_hash[1]

    device_id = update_device(hass, config_entry, config)
    if device_id is not None and device_id not in (tags := get_mqtt_data(hass).tags):
        tags[device_id] = {}

    tag_scanner = MQTTTagScanner(
        hass,
        config,
        device_id,
        discovery_data,
        config_entry,
    )

    await tag_scanner.subscribe_topics()

    if device_id:
        tags[device_id][discovery_id] = tag_scanner

    send_discovery_done(hass, discovery_data)


def async_has_tags(hass: HomeAssistant, device_id: str) -> bool:
    """Device has tag scanners."""
    if device_id not in (tags := get_mqtt_data(hass).tags):
        return False
    return tags[device_id] != {}


class MQTTTagScanner(MqttDiscoveryDeviceUpdate):
    """MQTT Tag scanner."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: ConfigType,
        device_id: str | None,
        discovery_data: dict,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize."""
        self._config = config
        self._config_entry = config_entry
        self.device_id = device_id
        self.discovery_data = discovery_data
        self.hass = hass
        self._sub_state: dict[str, EntitySubscription] | None = None
        self._value_template = MqttValueTemplate(
            config.get(CONF_VALUE_TEMPLATE),
            hass=self.hass,
        ).async_render_with_possible_json_value

        MqttDiscoveryDeviceUpdate.__init__(
            self, hass, discovery_data, device_id, config_entry, LOG_NAME
        )

    async def async_update(self, discovery_data: dict) -> None:
        """Handle MQTT tag discovery updates."""
        # Update tag scanner
        config = PLATFORM_SCHEMA(discovery_data)
        self._config = config
        self._value_template = MqttValueTemplate(
            config.get(CONF_VALUE_TEMPLATE),
            hass=self.hass,
        ).async_render_with_possible_json_value
        update_device(self.hass, self._config_entry, config)
        await self.subscribe_topics()

    async def subscribe_topics(self) -> None:
        """Subscribe to MQTT topics."""

        async def tag_scanned(msg: ReceiveMessage) -> None:
            tag_id = self._value_template(msg.payload, "").strip()
            if not tag_id:  # No output from template, ignore
                return

            # Importing tag via hass.components in case it is overridden
            # in a custom_components (custom_components.tag)
            tag = self.hass.components.tag
            await tag.async_scan_tag(tag_id, self.device_id)

        self._sub_state = subscription.async_prepare_subscribe_topics(
            self.hass,
            self._sub_state,
            {
                "state_topic": {
                    "topic": self._config[CONF_TOPIC],
                    "msg_callback": tag_scanned,
                    "qos": self._config[CONF_QOS],
                }
            },
        )
        await subscription.async_subscribe_topics(self.hass, self._sub_state)

    async def async_tear_down(self) -> None:
        """Cleanup tag scanner."""
        discovery_hash = self.discovery_data[ATTR_DISCOVERY_HASH]
        discovery_id = discovery_hash[1]
        self._sub_state = subscription.async_unsubscribe_topics(
            self.hass, self._sub_state
        )
        if self.device_id:
            get_mqtt_data(self.hass).tags[self.device_id].pop(discovery_id)
