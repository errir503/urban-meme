"""The Tasmota integration."""
from __future__ import annotations

import asyncio
import logging

from hatasmota.const import (
    CONF_IP,
    CONF_MAC,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_NAME,
    CONF_SW_VERSION,
)
from hatasmota.discovery import clear_discovery_topic
from hatasmota.models import TasmotaDeviceConfig
from hatasmota.mqtt import TasmotaMQTTClient
import voluptuous as vol

from homeassistant.components import mqtt, websocket_api
from homeassistant.components.mqtt.subscription import (
    async_prepare_subscribe_topics,
    async_subscribe_topics,
    async_unsubscribe_topics,
)
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    EVENT_DEVICE_REGISTRY_UPDATED,
    DeviceRegistry,
    async_entries_for_config_entry,
)

from . import device_automation, discovery
from .const import (
    CONF_DISCOVERY_PREFIX,
    DATA_REMOVE_DISCOVER_COMPONENT,
    DATA_UNSUB,
    DOMAIN,
    PLATFORMS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tasmota from a config entry."""
    websocket_api.async_register_command(hass, websocket_remove_device)
    hass.data[DATA_UNSUB] = []

    async def _publish(
        topic: str,
        payload: mqtt.PublishPayloadType,
        qos: int | None,
        retain: bool | None,
    ) -> None:
        await mqtt.async_publish(hass, topic, payload, qos, retain)

    async def _subscribe_topics(sub_state: dict | None, topics: dict) -> dict:
        # Optionally mark message handlers as callback
        for topic in topics.values():
            if "msg_callback" in topic and "event_loop_safe" in topic:
                topic["msg_callback"] = callback(topic["msg_callback"])
        sub_state = async_prepare_subscribe_topics(hass, sub_state, topics)
        await async_subscribe_topics(hass, sub_state)
        return sub_state

    async def _unsubscribe_topics(sub_state: dict | None) -> dict:
        return async_unsubscribe_topics(hass, sub_state)

    tasmota_mqtt = TasmotaMQTTClient(_publish, _subscribe_topics, _unsubscribe_topics)

    device_registry = dr.async_get(hass)

    async def async_discover_device(config: TasmotaDeviceConfig, mac: str) -> None:
        """Discover and add a Tasmota device."""
        await async_setup_device(
            hass, mac, config, entry, tasmota_mqtt, device_registry
        )

    async def async_device_updated(event: Event) -> None:
        """Handle the removal of a device."""
        device_registry = dr.async_get(hass)
        device_id = event.data["device_id"]
        if event.data["action"] not in ("remove", "update"):
            return

        connections: set[tuple[str, str]]
        if event.data["action"] == "update":
            if "config_entries" not in event.data["changes"]:
                return

            device = device_registry.async_get(device_id)
            if not device:
                # The device is already removed, do cleanup when we get "remove" event
                return
            if entry.entry_id in device.config_entries:
                # Not removed from device
                return
            connections = device.connections
        else:
            deleted_device = device_registry.deleted_devices[event.data["device_id"]]
            connections = deleted_device.connections
            if entry.entry_id not in deleted_device.config_entries:
                return

        macs = [c[1] for c in connections if c[0] == CONNECTION_NETWORK_MAC]
        for mac in macs:
            await clear_discovery_topic(
                mac, entry.data[CONF_DISCOVERY_PREFIX], tasmota_mqtt
            )

    hass.data[DATA_UNSUB].append(
        hass.bus.async_listen(EVENT_DEVICE_REGISTRY_UPDATED, async_device_updated)
    )

    async def start_platforms() -> None:
        await device_automation.async_setup_entry(hass, entry)
        await asyncio.gather(
            *(
                hass.config_entries.async_forward_entry_setup(entry, platform)
                for platform in PLATFORMS
            )
        )

        discovery_prefix = entry.data[CONF_DISCOVERY_PREFIX]
        await discovery.async_start(
            hass, discovery_prefix, entry, tasmota_mqtt, async_discover_device
        )

    hass.async_create_task(start_platforms())
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    # cleanup platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    # disable discovery
    await discovery.async_stop(hass)

    # cleanup subscriptions
    for unsub in hass.data[DATA_UNSUB]:
        unsub()
    hass.data.pop(DATA_REMOVE_DISCOVER_COMPONENT.format("device_automation"))()
    for platform in PLATFORMS:
        hass.data.pop(DATA_REMOVE_DISCOVER_COMPONENT.format(platform))()

    # deattach device triggers
    device_registry = dr.async_get(hass)
    devices = async_entries_for_config_entry(device_registry, entry.entry_id)
    for device in devices:
        await device_automation.async_remove_automations(hass, device.id)

    return True


async def _remove_device(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    mac: str,
    tasmota_mqtt: TasmotaMQTTClient,
    device_registry: DeviceRegistry,
) -> None:
    """Remove device from device registry."""
    device = device_registry.async_get_device(set(), {(CONNECTION_NETWORK_MAC, mac)})

    if device is None or config_entry.entry_id not in device.config_entries:
        return

    _LOGGER.debug("Removing tasmota from device %s", mac)
    device_registry.async_update_device(
        device.id, remove_config_entry_id=config_entry.entry_id
    )
    await clear_discovery_topic(
        mac, config_entry.data[CONF_DISCOVERY_PREFIX], tasmota_mqtt
    )


def _update_device(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    config: TasmotaDeviceConfig,
    device_registry: DeviceRegistry,
) -> None:
    """Add or update device registry."""
    _LOGGER.debug("Adding or updating tasmota device %s", config[CONF_MAC])
    device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        configuration_url=f"http://{config[CONF_IP]}/",
        connections={(CONNECTION_NETWORK_MAC, config[CONF_MAC])},
        manufacturer=config[CONF_MANUFACTURER],
        model=config[CONF_MODEL],
        name=config[CONF_NAME],
        sw_version=config[CONF_SW_VERSION],
    )


async def async_setup_device(
    hass: HomeAssistant,
    mac: str,
    config: TasmotaDeviceConfig,
    config_entry: ConfigEntry,
    tasmota_mqtt: TasmotaMQTTClient,
    device_registry: DeviceRegistry,
) -> None:
    """Set up the Tasmota device."""
    if not config:
        await _remove_device(hass, config_entry, mac, tasmota_mqtt, device_registry)
    else:
        _update_device(hass, config_entry, config, device_registry)


@websocket_api.websocket_command(
    {vol.Required("type"): "tasmota/device/remove", vol.Required("device_id"): str}
)
@callback
def websocket_remove_device(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict
) -> None:
    """Delete device."""
    device_id = msg["device_id"]
    dev_registry = dr.async_get(hass)

    if not (device := dev_registry.async_get(device_id)):
        connection.send_error(
            msg["id"], websocket_api.const.ERR_NOT_FOUND, "Device not found"
        )
        return

    for config_entry_id in device.config_entries:
        config_entry = hass.config_entries.async_get_entry(config_entry_id)
        assert config_entry
        # Only delete the device if it belongs to a Tasmota device entry
        if config_entry.domain == DOMAIN:
            dev_registry.async_remove_device(device_id)
            connection.send_message(websocket_api.result_message(msg["id"]))
            return

    connection.send_error(
        msg["id"], websocket_api.const.ERR_NOT_FOUND, "Non Tasmota device"
    )


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Remove Tasmota config entry from a device."""
    # Just return True, cleanup is done on when handling device registry events
    return True
