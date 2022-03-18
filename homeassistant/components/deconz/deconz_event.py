"""Representation of a deCONZ remote or keypad."""

from __future__ import annotations

from pydeconz.sensor import (
    ANCILLARY_CONTROL_EMERGENCY,
    ANCILLARY_CONTROL_FIRE,
    ANCILLARY_CONTROL_INVALID_CODE,
    ANCILLARY_CONTROL_PANIC,
    AncillaryControl,
    Switch,
)

from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_EVENT,
    CONF_ID,
    CONF_UNIQUE_ID,
    CONF_XY,
)
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util import slugify

from .const import CONF_ANGLE, CONF_GESTURE, LOGGER
from .deconz_device import DeconzBase
from .gateway import DeconzGateway

CONF_DECONZ_EVENT = "deconz_event"
CONF_DECONZ_ALARM_EVENT = "deconz_alarm_event"

SUPPORTED_DECONZ_ALARM_EVENTS = {
    ANCILLARY_CONTROL_EMERGENCY,
    ANCILLARY_CONTROL_FIRE,
    ANCILLARY_CONTROL_INVALID_CODE,
    ANCILLARY_CONTROL_PANIC,
}


async def async_setup_events(gateway: DeconzGateway) -> None:
    """Set up the deCONZ events."""

    @callback
    def async_add_sensor(
        sensors: AncillaryControl | Switch = gateway.api.sensors.values(),
    ) -> None:
        """Create DeconzEvent."""
        new_events = []
        known_events = {event.unique_id for event in gateway.events}

        for sensor in sensors:

            if not gateway.option_allow_clip_sensor and sensor.type.startswith("CLIP"):
                continue

            if sensor.unique_id in known_events:
                continue

            if isinstance(sensor, Switch):
                new_events.append(DeconzEvent(sensor, gateway))

            elif isinstance(sensor, AncillaryControl):
                new_events.append(DeconzAlarmEvent(sensor, gateway))

        for new_event in new_events:
            gateway.hass.async_create_task(new_event.async_update_device_registry())
            gateway.events.append(new_event)

    gateway.config_entry.async_on_unload(
        async_dispatcher_connect(
            gateway.hass,
            gateway.signal_new_sensor,
            async_add_sensor,
        )
    )

    async_add_sensor()


@callback
def async_unload_events(gateway: DeconzGateway) -> None:
    """Unload all deCONZ events."""
    for event in gateway.events:
        event.async_will_remove_from_hass()

    gateway.events.clear()


class DeconzEvent(DeconzBase):
    """When you want signals instead of entities.

    Stateless sensors such as remotes are expected to generate an event
    instead of a sensor entity in hass.
    """

    def __init__(
        self,
        device: AncillaryControl | Switch,
        gateway: DeconzGateway,
    ) -> None:
        """Register callback that will be used for signals."""
        super().__init__(device, gateway)

        self._device.register_callback(self.async_update_callback)

        self.device_id: str | None = None
        self.event_id = slugify(self._device.name)
        LOGGER.debug("deCONZ event created: %s", self.event_id)

    @property
    def device(self) -> AncillaryControl | Switch:
        """Return Event device."""
        return self._device

    @callback
    def async_will_remove_from_hass(self) -> None:
        """Disconnect event object when removed."""
        self._device.remove_callback(self.async_update_callback)

    @callback
    def async_update_callback(self) -> None:
        """Fire the event if reason is that state is updated."""
        if (
            self.gateway.ignore_state_updates
            or "state" not in self._device.changed_keys
        ):
            return

        data = {
            CONF_ID: self.event_id,
            CONF_UNIQUE_ID: self.serial,
            CONF_EVENT: self._device.state,
        }

        if self.device_id:
            data[CONF_DEVICE_ID] = self.device_id

        if self._device.gesture is not None:
            data[CONF_GESTURE] = self._device.gesture

        if self._device.angle is not None:
            data[CONF_ANGLE] = self._device.angle

        if self._device.xy is not None:
            data[CONF_XY] = self._device.xy

        self.gateway.hass.bus.async_fire(CONF_DECONZ_EVENT, data)

    async def async_update_device_registry(self) -> None:
        """Update device registry."""
        if not self.device_info:
            return

        device_registry = dr.async_get(self.gateway.hass)

        entry = device_registry.async_get_or_create(
            config_entry_id=self.gateway.config_entry.entry_id, **self.device_info
        )
        self.device_id = entry.id


class DeconzAlarmEvent(DeconzEvent):
    """Alarm control panel companion event when user interacts with a keypad."""

    _device: AncillaryControl

    @callback
    def async_update_callback(self) -> None:
        """Fire the event if reason is new action is updated."""
        if (
            self.gateway.ignore_state_updates
            or "action" not in self._device.changed_keys
            or self._device.action not in SUPPORTED_DECONZ_ALARM_EVENTS
        ):
            return

        data = {
            CONF_ID: self.event_id,
            CONF_UNIQUE_ID: self.serial,
            CONF_DEVICE_ID: self.device_id,
            CONF_EVENT: self._device.action,
        }

        self.gateway.hass.bus.async_fire(CONF_DECONZ_ALARM_EVENT, data)
