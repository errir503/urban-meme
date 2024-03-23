"""Support for Axis lights."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import partial
from typing import Any

from axis.models.event import Event, EventOperation, EventTopic

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
    LightEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import TOPIC_TO_EVENT_TYPE, AxisEventEntity
from .hub import AxisHub


@callback
def light_name_fn(hub: AxisHub, event: Event) -> str:
    """Provide Axis light entity name."""
    event_type = TOPIC_TO_EVENT_TYPE[event.topic_base]
    light_id = f"led{event.id}"
    light_type = hub.api.vapix.light_control[light_id].light_type
    return f"{light_type} {event_type} {event.id}"


@dataclass(frozen=True, kw_only=True)
class AxisLightDescription(LightEntityDescription):
    """Axis light entity description."""

    event_topic: EventTopic
    """Event topic that provides state updates."""
    name_fn: Callable[[AxisHub, Event], str]
    """Function providing the corresponding name to the event ID."""
    supported_fn: Callable[[AxisHub, Event], bool]
    """Function validating if event is supported."""


ENTITY_DESCRIPTIONS = (
    AxisLightDescription(
        key="Light state control",
        event_topic=EventTopic.LIGHT_STATUS,
        name_fn=light_name_fn,
        supported_fn=lambda hub, event: len(hub.api.vapix.light_control) > 0,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Axis light platform."""
    hub = AxisHub.get_hub(hass, config_entry)

    @callback
    def register_platform(descriptions: Iterable[AxisLightDescription]) -> None:
        """Register entity platform to create entities on event initialized signal."""

        @callback
        def create_entity(description: AxisLightDescription, event: Event) -> None:
            """Create Axis entity."""
            if description.supported_fn(hub, event):
                async_add_entities([AxisLight(hub, description, event)])

        for description in descriptions:
            hub.api.event.subscribe(
                partial(create_entity, description),
                topic_filter=description.event_topic,
                operation_filter=EventOperation.INITIALIZED,
            )

    register_platform(ENTITY_DESCRIPTIONS)


class AxisLight(AxisEventEntity, LightEntity):
    """Representation of an Axis light."""

    _attr_should_poll = True
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(
        self, hub: AxisHub, description: AxisLightDescription, event: Event
    ) -> None:
        """Initialize the Axis light."""
        super().__init__(event, hub)
        self.entity_description = description
        self._attr_name = description.name_fn(hub, event)
        self._attr_is_on = event.is_tripped

        self._light_id = f"led{event.id}"
        self.current_intensity = 0
        self.max_intensity = 0

    async def async_added_to_hass(self) -> None:
        """Subscribe lights events."""
        await super().async_added_to_hass()
        self.current_intensity = (
            await self.hub.api.vapix.light_control.get_current_intensity(self._light_id)
        )
        self.max_intensity = (
            await self.hub.api.vapix.light_control.get_valid_intensity(self._light_id)
        ).high

    @callback
    def async_event_callback(self, event: Event) -> None:
        """Update light state."""
        self._attr_is_on = event.is_tripped
        self.async_write_ha_state()

    @property
    def brightness(self) -> int:
        """Return the brightness of this light between 0..255."""
        return int((self.current_intensity / self.max_intensity) * 255)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on light."""
        if not self.is_on:
            await self.hub.api.vapix.light_control.activate_light(self._light_id)

        if ATTR_BRIGHTNESS in kwargs:
            intensity = int((kwargs[ATTR_BRIGHTNESS] / 255) * self.max_intensity)
            await self.hub.api.vapix.light_control.set_manual_intensity(
                self._light_id, intensity
            )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off light."""
        if self.is_on:
            await self.hub.api.vapix.light_control.deactivate_light(self._light_id)

    async def async_update(self) -> None:
        """Update brightness."""
        self.current_intensity = (
            await self.hub.api.vapix.light_control.get_current_intensity(self._light_id)
        )
