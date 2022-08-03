"""Support for Axis binary sensors."""
from __future__ import annotations

from datetime import timedelta

from axis.event_stream import (
    CLASS_INPUT,
    CLASS_LIGHT,
    CLASS_MOTION,
    CLASS_OUTPUT,
    CLASS_PTZ,
    CLASS_SOUND,
    AxisBinaryEvent,
    AxisEvent,
    FenceGuard,
    LoiteringGuard,
    MotionGuard,
    ObjectAnalytics,
    Vmd4,
)

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util.dt import utcnow

from .axis_base import AxisEventBase
from .const import DOMAIN as AXIS_DOMAIN
from .device import AxisNetworkDevice

DEVICE_CLASS = {
    CLASS_INPUT: BinarySensorDeviceClass.CONNECTIVITY,
    CLASS_LIGHT: BinarySensorDeviceClass.LIGHT,
    CLASS_MOTION: BinarySensorDeviceClass.MOTION,
    CLASS_SOUND: BinarySensorDeviceClass.SOUND,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a Axis binary sensor."""
    device: AxisNetworkDevice = hass.data[AXIS_DOMAIN][config_entry.unique_id]

    @callback
    def async_add_sensor(event_id):
        """Add binary sensor from Axis device."""
        event: AxisEvent = device.api.event[event_id]

        if event.CLASS not in (CLASS_OUTPUT, CLASS_PTZ) and not (
            event.CLASS == CLASS_LIGHT and event.TYPE == "Light"
        ):
            async_add_entities([AxisBinarySensor(event, device)])

    config_entry.async_on_unload(
        async_dispatcher_connect(hass, device.signal_new_event, async_add_sensor)
    )


class AxisBinarySensor(AxisEventBase, BinarySensorEntity):
    """Representation of a binary Axis event."""

    event: AxisBinaryEvent

    def __init__(self, event: AxisEvent, device: AxisNetworkDevice) -> None:
        """Initialize the Axis binary sensor."""
        super().__init__(event, device)
        self.cancel_scheduled_update = None

        self._attr_device_class = DEVICE_CLASS.get(self.event.CLASS)

    @callback
    def update_callback(self, no_delay=False):
        """Update the sensor's state, if needed.

        Parameter no_delay is True when device_event_reachable is sent.
        """

        @callback
        def scheduled_update(now):
            """Timer callback for sensor update."""
            self.cancel_scheduled_update = None
            self.async_write_ha_state()

        if self.cancel_scheduled_update is not None:
            self.cancel_scheduled_update()
            self.cancel_scheduled_update = None

        if self.is_on or self.device.option_trigger_time == 0 or no_delay:
            self.async_write_ha_state()
            return

        self.cancel_scheduled_update = async_track_point_in_utc_time(
            self.hass,
            scheduled_update,
            utcnow() + timedelta(seconds=self.device.option_trigger_time),
        )

    @property
    def is_on(self) -> bool:
        """Return true if event is active."""
        return self.event.is_tripped

    @property
    def name(self) -> str | None:
        """Return the name of the event."""
        if (
            self.event.CLASS == CLASS_INPUT
            and self.event.id in self.device.api.vapix.ports
            and self.device.api.vapix.ports[self.event.id].name
        ):
            return self.device.api.vapix.ports[self.event.id].name

        if self.event.CLASS == CLASS_MOTION:

            for event_class, event_data in (
                (FenceGuard, self.device.api.vapix.fence_guard),
                (LoiteringGuard, self.device.api.vapix.loitering_guard),
                (MotionGuard, self.device.api.vapix.motion_guard),
                (ObjectAnalytics, self.device.api.vapix.object_analytics),
                (Vmd4, self.device.api.vapix.vmd4),
            ):
                if (
                    isinstance(self.event, event_class)
                    and event_data
                    and self.event.id in event_data
                ):
                    return f"{self.event.TYPE} {event_data[self.event.id].name}"

        return self._attr_name
