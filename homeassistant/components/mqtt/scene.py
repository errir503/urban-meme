"""Support for MQTT scenes."""
from __future__ import annotations

import functools
from typing import Any

import voluptuous as vol

from homeassistant.components import scene
from homeassistant.components.scene import Scene
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ICON, CONF_NAME, CONF_PAYLOAD_ON, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .client import async_publish
from .config import MQTT_BASE_SCHEMA
from .const import CONF_COMMAND_TOPIC, CONF_ENCODING, CONF_QOS, CONF_RETAIN
from .mixins import (
    CONF_ENABLED_BY_DEFAULT,
    CONF_OBJECT_ID,
    MQTT_AVAILABILITY_SCHEMA,
    MqttEntity,
    async_setup_entry_helper,
    warn_for_legacy_schema,
)
from .util import valid_publish_topic

DEFAULT_NAME = "MQTT Scene"
DEFAULT_RETAIN = False

PLATFORM_SCHEMA_MODERN = MQTT_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_COMMAND_TOPIC): valid_publish_topic,
        vol.Optional(CONF_ICON): cv.icon,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_PAYLOAD_ON): cv.string,
        vol.Optional(CONF_UNIQUE_ID): cv.string,
        vol.Optional(CONF_RETAIN, default=DEFAULT_RETAIN): cv.boolean,
        vol.Optional(CONF_OBJECT_ID): cv.string,
        # CONF_ENABLED_BY_DEFAULT is not added by default because we are not using the common schema here
        vol.Optional(CONF_ENABLED_BY_DEFAULT, default=True): cv.boolean,
    }
).extend(MQTT_AVAILABILITY_SCHEMA.schema)

# Configuring MQTT Scenes under the scene platform key was deprecated in HA Core 2022.6
# Setup for the legacy YAML format was removed in HA Core 2022.12
PLATFORM_SCHEMA = vol.All(
    warn_for_legacy_schema(scene.DOMAIN),
)

DISCOVERY_SCHEMA = PLATFORM_SCHEMA_MODERN.extend({}, extra=vol.REMOVE_EXTRA)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MQTT scene through configuration.yaml and dynamically through MQTT discovery."""
    setup = functools.partial(
        _async_setup_entity, hass, async_add_entities, config_entry=config_entry
    )
    await async_setup_entry_helper(hass, scene.DOMAIN, setup, DISCOVERY_SCHEMA)


async def _async_setup_entity(
    hass: HomeAssistant,
    async_add_entities: AddEntitiesCallback,
    config: ConfigType,
    config_entry: ConfigEntry,
    discovery_data: DiscoveryInfoType | None = None,
) -> None:
    """Set up the MQTT scene."""
    async_add_entities([MqttScene(hass, config, config_entry, discovery_data)])


class MqttScene(
    MqttEntity,
    Scene,
):
    """Representation of a scene that can be activated using MQTT."""

    _entity_id_format = scene.DOMAIN + ".{}"

    def __init__(
        self,
        hass: HomeAssistant,
        config: ConfigType,
        config_entry: ConfigEntry,
        discovery_data: DiscoveryInfoType | None,
    ) -> None:
        """Initialize the MQTT scene."""
        MqttEntity.__init__(self, hass, config, config_entry, discovery_data)

    @staticmethod
    def config_schema() -> vol.Schema:
        """Return the config schema."""
        return DISCOVERY_SCHEMA

    def _setup_from_config(self, config: ConfigType) -> None:
        """(Re)Setup the entity."""
        self._config = config

    def _prepare_subscribe_topics(self) -> None:
        """(Re)Subscribe to topics."""

    async def _subscribe_topics(self) -> None:
        """(Re)Subscribe to topics."""

    async def async_activate(self, **kwargs: Any) -> None:
        """Activate the scene.

        This method is a coroutine.
        """
        await async_publish(
            self.hass,
            self._config[CONF_COMMAND_TOPIC],
            self._config[CONF_PAYLOAD_ON],
            self._config[CONF_QOS],
            self._config[CONF_RETAIN],
            self._config[CONF_ENCODING],
        )
