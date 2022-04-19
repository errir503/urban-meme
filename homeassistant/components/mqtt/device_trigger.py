"""Provides device automations for MQTT."""
from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any, cast

import attr
import voluptuous as vol

from homeassistant.components.automation import (
    AutomationActionType,
    AutomationTriggerInfo,
)
from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DEVICE,
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_PLATFORM,
    CONF_TYPE,
    CONF_VALUE_TEMPLATE,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.typing import ConfigType

from . import debug_info, trigger as mqtt_trigger
from .. import mqtt
from .const import ATTR_DISCOVERY_HASH, CONF_PAYLOAD, CONF_QOS, CONF_TOPIC, DOMAIN
from .discovery import MQTT_DISCOVERY_DONE
from .mixins import (
    MQTT_ENTITY_DEVICE_INFO_SCHEMA,
    MqttDiscoveryDeviceUpdate,
    send_discovery_done,
    update_device,
)

_LOGGER = logging.getLogger(__name__)

CONF_AUTOMATION_TYPE = "automation_type"
CONF_DISCOVERY_ID = "discovery_id"
CONF_SUBTYPE = "subtype"
DEFAULT_ENCODING = "utf-8"
DEVICE = "device"

MQTT_TRIGGER_BASE = {
    # Trigger when MQTT message is received
    CONF_PLATFORM: DEVICE,
    CONF_DOMAIN: DOMAIN,
}

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_PLATFORM): DEVICE,
        vol.Required(CONF_DOMAIN): DOMAIN,
        vol.Required(CONF_DEVICE_ID): str,
        vol.Required(CONF_DISCOVERY_ID): str,
        vol.Required(CONF_TYPE): cv.string,
        vol.Required(CONF_SUBTYPE): cv.string,
    }
)

TRIGGER_DISCOVERY_SCHEMA = mqtt.MQTT_BASE_PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_AUTOMATION_TYPE): str,
        vol.Required(CONF_DEVICE): MQTT_ENTITY_DEVICE_INFO_SCHEMA,
        vol.Optional(CONF_PAYLOAD, default=None): vol.Any(None, cv.string),
        vol.Required(CONF_SUBTYPE): cv.string,
        vol.Required(CONF_TOPIC): cv.string,
        vol.Required(CONF_TYPE): cv.string,
        vol.Optional(CONF_VALUE_TEMPLATE, default=None): vol.Any(None, cv.string),
    },
    extra=vol.REMOVE_EXTRA,
)

DEVICE_TRIGGERS = "mqtt_device_triggers"

LOG_NAME = "Device trigger"


@attr.s(slots=True)
class TriggerInstance:
    """Attached trigger settings."""

    action: AutomationActionType = attr.ib()
    automation_info: AutomationTriggerInfo = attr.ib()
    trigger: Trigger = attr.ib()
    remove: CALLBACK_TYPE | None = attr.ib(default=None)

    async def async_attach_trigger(self) -> None:
        """Attach MQTT trigger."""
        mqtt_config = {
            mqtt_trigger.CONF_PLATFORM: mqtt.DOMAIN,
            mqtt_trigger.CONF_TOPIC: self.trigger.topic,
            mqtt_trigger.CONF_ENCODING: DEFAULT_ENCODING,
            mqtt_trigger.CONF_QOS: self.trigger.qos,
        }
        if self.trigger.payload:
            mqtt_config[CONF_PAYLOAD] = self.trigger.payload
        if self.trigger.value_template:
            mqtt_config[CONF_VALUE_TEMPLATE] = self.trigger.value_template
        mqtt_config = mqtt_trigger.TRIGGER_SCHEMA(mqtt_config)

        if self.remove:
            self.remove()
        self.remove = await mqtt_trigger.async_attach_trigger(
            self.trigger.hass,
            mqtt_config,
            self.action,
            self.automation_info,
        )


@attr.s(slots=True)
class Trigger:
    """Device trigger settings."""

    device_id: str = attr.ib()
    discovery_data: dict | None = attr.ib()
    hass: HomeAssistant = attr.ib()
    payload: str | None = attr.ib()
    qos: int | None = attr.ib()
    subtype: str = attr.ib()
    topic: str | None = attr.ib()
    type: str = attr.ib()
    value_template: str | None = attr.ib()
    trigger_instances: list[TriggerInstance] = attr.ib(factory=list)

    async def add_trigger(
        self, action: AutomationActionType, automation_info: AutomationTriggerInfo
    ) -> Callable:
        """Add MQTT trigger."""
        instance = TriggerInstance(action, automation_info, self)
        self.trigger_instances.append(instance)

        if self.topic is not None:
            # If we know about the trigger, subscribe to MQTT topic
            await instance.async_attach_trigger()

        @callback
        def async_remove() -> None:
            """Remove trigger."""
            if instance not in self.trigger_instances:
                raise HomeAssistantError("Can't remove trigger twice")

            if instance.remove:
                instance.remove()
            self.trigger_instances.remove(instance)

        return async_remove

    async def update_trigger(self, config: ConfigType) -> None:
        """Update MQTT device trigger."""
        self.type = config[CONF_TYPE]
        self.subtype = config[CONF_SUBTYPE]
        self.payload = config[CONF_PAYLOAD]
        self.qos = config[CONF_QOS]
        topic_changed = self.topic != config[CONF_TOPIC]
        self.topic = config[CONF_TOPIC]
        self.value_template = config[CONF_VALUE_TEMPLATE]

        # Unsubscribe+subscribe if this trigger is in use and topic has changed
        # If topic is same unsubscribe+subscribe will execute in the wrong order
        # because unsubscribe is done with help of async_create_task
        if topic_changed:
            for trig in self.trigger_instances:
                await trig.async_attach_trigger()

    def detach_trigger(self) -> None:
        """Remove MQTT device trigger."""
        # Mark trigger as unknown
        self.topic = None

        # Unsubscribe if this trigger is in use
        for trig in self.trigger_instances:
            if trig.remove:
                trig.remove()
                trig.remove = None


class MqttDeviceTrigger(MqttDiscoveryDeviceUpdate):
    """Setup a MQTT device trigger with auto discovery."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: ConfigType,
        device_id: str,
        discovery_data: dict,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize."""
        self._config = config
        self._config_entry = config_entry
        self.device_id = device_id
        self.discovery_data = discovery_data
        self.hass = hass

        MqttDiscoveryDeviceUpdate.__init__(
            self,
            hass,
            discovery_data,
            device_id,
            config_entry,
            LOG_NAME,
        )

    async def async_setup(self) -> None:
        """Initialize the device trigger."""
        discovery_hash = self.discovery_data[ATTR_DISCOVERY_HASH]
        discovery_id = discovery_hash[1]
        if discovery_id not in self.hass.data.setdefault(DEVICE_TRIGGERS, {}):
            self.hass.data[DEVICE_TRIGGERS][discovery_id] = Trigger(
                hass=self.hass,
                device_id=self.device_id,
                discovery_data=self.discovery_data,
                type=self._config[CONF_TYPE],
                subtype=self._config[CONF_SUBTYPE],
                topic=self._config[CONF_TOPIC],
                payload=self._config[CONF_PAYLOAD],
                qos=self._config[CONF_QOS],
                value_template=self._config[CONF_VALUE_TEMPLATE],
            )
        else:
            await self.hass.data[DEVICE_TRIGGERS][discovery_id].update_trigger(
                self._config
            )
        debug_info.add_trigger_discovery_data(
            self.hass, discovery_hash, self.discovery_data, self.device_id
        )

    async def async_update(self, discovery_data: dict) -> None:
        """Handle MQTT device trigger discovery updates."""
        discovery_hash = self.discovery_data[ATTR_DISCOVERY_HASH]
        discovery_id = discovery_hash[1]
        debug_info.update_trigger_discovery_data(
            self.hass, discovery_hash, discovery_data
        )
        config = TRIGGER_DISCOVERY_SCHEMA(discovery_data)
        update_device(self.hass, self._config_entry, config)
        device_trigger: Trigger = self.hass.data[DEVICE_TRIGGERS][discovery_id]
        await device_trigger.update_trigger(config)

    async def async_tear_down(self) -> None:
        """Cleanup device trigger."""
        discovery_hash = self.discovery_data[ATTR_DISCOVERY_HASH]
        discovery_id = discovery_hash[1]
        if discovery_id in self.hass.data[DEVICE_TRIGGERS]:
            _LOGGER.info("Removing trigger: %s", discovery_hash)
            trigger: Trigger = self.hass.data[DEVICE_TRIGGERS][discovery_id]
            trigger.detach_trigger()
            debug_info.remove_trigger_discovery_data(self.hass, discovery_hash)


async def async_setup_trigger(
    hass, config: ConfigType, config_entry: ConfigEntry, discovery_data: dict
) -> None:
    """Set up the MQTT device trigger."""
    config = TRIGGER_DISCOVERY_SCHEMA(config)
    discovery_hash = discovery_data[ATTR_DISCOVERY_HASH]

    if (device_id := update_device(hass, config_entry, config)) is None:
        async_dispatcher_send(hass, MQTT_DISCOVERY_DONE.format(discovery_hash), None)
        return

    mqtt_device_trigger = MqttDeviceTrigger(
        hass, config, device_id, discovery_data, config_entry
    )
    await mqtt_device_trigger.async_setup()
    send_discovery_done(hass, discovery_data)


async def async_removed_from_device(hass: HomeAssistant, device_id: str) -> None:
    """Handle Mqtt removed from a device."""
    triggers = await async_get_triggers(hass, device_id)
    for trig in triggers:
        device_trigger: Trigger = hass.data[DEVICE_TRIGGERS].pop(
            trig[CONF_DISCOVERY_ID]
        )
        if device_trigger:
            device_trigger.detach_trigger()
            discovery_data = cast(dict, device_trigger.discovery_data)
            discovery_hash = discovery_data[ATTR_DISCOVERY_HASH]
            debug_info.remove_trigger_discovery_data(hass, discovery_hash)


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """List device triggers for MQTT devices."""
    triggers: list[dict] = []

    if DEVICE_TRIGGERS not in hass.data:
        return triggers

    for discovery_id, trig in hass.data[DEVICE_TRIGGERS].items():
        if trig.device_id != device_id or trig.topic is None:
            continue

        trigger = {
            **MQTT_TRIGGER_BASE,
            "device_id": device_id,
            "type": trig.type,
            "subtype": trig.subtype,
            "discovery_id": discovery_id,
        }
        triggers.append(trigger)

    return triggers


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: AutomationActionType,
    automation_info: AutomationTriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a trigger."""
    hass.data.setdefault(DEVICE_TRIGGERS, {})
    device_id = config[CONF_DEVICE_ID]
    discovery_id = config[CONF_DISCOVERY_ID]

    if discovery_id not in hass.data[DEVICE_TRIGGERS]:
        hass.data[DEVICE_TRIGGERS][discovery_id] = Trigger(
            hass=hass,
            device_id=device_id,
            discovery_data=None,
            type=config[CONF_TYPE],
            subtype=config[CONF_SUBTYPE],
            topic=None,
            payload=None,
            qos=None,
            value_template=None,
        )
    return await hass.data[DEVICE_TRIGGERS][discovery_id].add_trigger(
        action, automation_info
    )
