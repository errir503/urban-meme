"""Support for Axis binary sensors."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial

from axis.models.event import Event, EventOperation, EventTopic
from axis.vapix.interfaces.applications.fence_guard import FenceGuardHandler
from axis.vapix.interfaces.applications.loitering_guard import LoiteringGuardHandler
from axis.vapix.interfaces.applications.motion_guard import MotionGuardHandler
from axis.vapix.interfaces.applications.vmd4 import Vmd4Handler

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .entity import AxisEventDescription, AxisEventEntity
from .hub import AxisHub


@dataclass(frozen=True, kw_only=True)
class AxisBinarySensorDescription(AxisEventDescription, BinarySensorEntityDescription):
    """Axis binary sensor entity description."""


@callback
def event_id_is_int(event_id: str) -> bool:
    """Make sure event ID is int."""
    try:
        _ = int(event_id)
    except ValueError:
        return False
    return True


@callback
def guard_suite_supported_fn(hub: AxisHub, event: Event) -> bool:
    """Validate event ID is int."""
    _, _, profile_id = event.id.partition("Profile")
    return event_id_is_int(profile_id)


@callback
def object_analytics_supported_fn(hub: AxisHub, event: Event) -> bool:
    """Validate event ID is int."""
    _, _, profile_id = event.id.partition("Scenario")
    return event_id_is_int(profile_id)


@callback
def guard_suite_name_fn(
    handler: FenceGuardHandler
    | LoiteringGuardHandler
    | MotionGuardHandler
    | Vmd4Handler,
    event: Event,
    event_type: str,
) -> str:
    """Get guard suite item name."""
    if handler.initialized and (profiles := handler["0"].profiles):
        for profile_id, profile in profiles.items():
            camera_id = profile.camera
            if event.id == f"Camera{camera_id}Profile{profile_id}":
                return f"{event_type} {profile.name}"
    return ""


@callback
def fence_guard_name_fn(hub: AxisHub, event: Event) -> str:
    """Fence guard name."""
    return guard_suite_name_fn(hub.api.vapix.fence_guard, event, "Fence Guard")


@callback
def loitering_guard_name_fn(hub: AxisHub, event: Event) -> str:
    """Loitering guard name."""
    return guard_suite_name_fn(hub.api.vapix.loitering_guard, event, "Loitering Guard")


@callback
def motion_guard_name_fn(hub: AxisHub, event: Event) -> str:
    """Motion guard name."""
    return guard_suite_name_fn(hub.api.vapix.motion_guard, event, "Motion Guard")


@callback
def motion_detection_4_name_fn(hub: AxisHub, event: Event) -> str:
    """Motion detection 4 name."""
    return guard_suite_name_fn(hub.api.vapix.vmd4, event, "VMD4")


@callback
def object_analytics_name_fn(hub: AxisHub, event: Event) -> str:
    """Get object analytics name."""
    if hub.api.vapix.object_analytics.initialized and (
        scenarios := hub.api.vapix.object_analytics["0"].scenarios
    ):
        for scenario_id, scenario in scenarios.items():
            device_id = scenario.devices[0]["id"]
            if event.id == f"Device{device_id}Scenario{scenario_id}":
                return f"Object Analytics {scenario.name}"
    return ""


ENTITY_DESCRIPTIONS = (
    AxisBinarySensorDescription(
        key="Input port state",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        event_topic=(EventTopic.PORT_INPUT, EventTopic.PORT_SUPERVISED_INPUT),
        name_fn=lambda hub, event: hub.api.vapix.ports[event.id].name,
        supported_fn=lambda hub, event: event_id_is_int(event.id),
    ),
    AxisBinarySensorDescription(
        key="Day/Night vision state",
        device_class=BinarySensorDeviceClass.LIGHT,
        event_topic=EventTopic.DAY_NIGHT_VISION,
    ),
    AxisBinarySensorDescription(
        key="Sound trigger state",
        device_class=BinarySensorDeviceClass.SOUND,
        event_topic=EventTopic.SOUND_TRIGGER_LEVEL,
    ),
    AxisBinarySensorDescription(
        key="Motion sensors state",
        device_class=BinarySensorDeviceClass.MOTION,
        event_topic=(
            EventTopic.PIR,
            EventTopic.MOTION_DETECTION,
            EventTopic.MOTION_DETECTION_3,
        ),
    ),
    AxisBinarySensorDescription(
        key="Motion detection 4 state",
        device_class=BinarySensorDeviceClass.MOTION,
        event_topic=EventTopic.MOTION_DETECTION_4,
        name_fn=motion_detection_4_name_fn,
        supported_fn=guard_suite_supported_fn,
    ),
    AxisBinarySensorDescription(
        key="Fence guard state",
        device_class=BinarySensorDeviceClass.MOTION,
        event_topic=EventTopic.FENCE_GUARD,
        name_fn=fence_guard_name_fn,
        supported_fn=guard_suite_supported_fn,
    ),
    AxisBinarySensorDescription(
        key="Loitering guard state",
        device_class=BinarySensorDeviceClass.MOTION,
        event_topic=EventTopic.LOITERING_GUARD,
        name_fn=loitering_guard_name_fn,
        supported_fn=guard_suite_supported_fn,
    ),
    AxisBinarySensorDescription(
        key="Motion guard state",
        device_class=BinarySensorDeviceClass.MOTION,
        event_topic=EventTopic.MOTION_GUARD,
        name_fn=motion_guard_name_fn,
        supported_fn=guard_suite_supported_fn,
    ),
    AxisBinarySensorDescription(
        key="Object analytics state",
        device_class=BinarySensorDeviceClass.MOTION,
        event_topic=EventTopic.OBJECT_ANALYTICS,
        name_fn=object_analytics_name_fn,
        supported_fn=object_analytics_supported_fn,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a Axis binary sensor."""
    hub = AxisHub.get_hub(hass, config_entry)

    @callback
    def register_platform(descriptions: Iterable[AxisBinarySensorDescription]) -> None:
        """Register entity platform to create entities on event initialized signal."""

        @callback
        def create_entity(
            description: AxisBinarySensorDescription, event: Event
        ) -> None:
            """Create Axis entity."""
            if description.supported_fn(hub, event):
                async_add_entities([AxisBinarySensor(hub, description, event)])

        for description in descriptions:
            hub.api.event.subscribe(
                partial(create_entity, description),
                topic_filter=description.event_topic,
                operation_filter=EventOperation.INITIALIZED,
            )

    register_platform(ENTITY_DESCRIPTIONS)


class AxisBinarySensor(AxisEventEntity, BinarySensorEntity):
    """Representation of a binary Axis event."""

    entity_description: AxisBinarySensorDescription

    def __init__(
        self, hub: AxisHub, description: AxisBinarySensorDescription, event: Event
    ) -> None:
        """Initialize the Axis binary sensor."""
        super().__init__(hub, description, event)

        self._attr_is_on = event.is_tripped
        self.cancel_scheduled_update: Callable[[], None] | None = None

    @callback
    def async_event_callback(self, event: Event) -> None:
        """Update the sensor's state, if needed."""
        self._attr_is_on = event.is_tripped

        @callback
        def scheduled_update(now: datetime) -> None:
            """Timer callback for sensor update."""
            self.cancel_scheduled_update = None
            self.async_write_ha_state()

        if self.cancel_scheduled_update is not None:
            self.cancel_scheduled_update()
            self.cancel_scheduled_update = None

        if self.is_on or self.hub.config.trigger_time == 0:
            self.async_write_ha_state()
            return

        self.cancel_scheduled_update = async_call_later(
            self.hass,
            timedelta(seconds=self.hub.config.trigger_time),
            scheduled_update,
        )
