"""Offer calendar automation rules."""
from __future__ import annotations

import datetime
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.automation import (
    AutomationActionType,
    AutomationTriggerInfo,
)
from homeassistant.const import CONF_ENTITY_ID, CONF_EVENT, CONF_PLATFORM
from homeassistant.core import CALLBACK_TYPE, HassJob, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_time_interval,
)
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from . import DOMAIN, CalendarEntity, CalendarEvent

_LOGGER = logging.getLogger(__name__)

EVENT_START = "start"
EVENT_END = "end"
UPDATE_INTERVAL = datetime.timedelta(minutes=15)

TRIGGER_SCHEMA = cv.TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_PLATFORM): DOMAIN,
        vol.Required(CONF_ENTITY_ID): cv.entity_id,
        vol.Optional(CONF_EVENT, default=EVENT_START): vol.In({EVENT_START, EVENT_END}),
    }
)


class CalendarEventListener:
    """Helper class to listen to calendar events."""

    def __init__(
        self,
        hass: HomeAssistant,
        job: HassJob,
        trigger_data: dict[str, Any],
        entity: CalendarEntity,
        event_type: str,
    ) -> None:
        """Initialize CalendarEventListener."""
        self._hass = hass
        self._job = job
        self._trigger_data = trigger_data
        self._entity = entity
        self._unsub_event: CALLBACK_TYPE | None = None
        self._unsub_refresh: CALLBACK_TYPE | None = None
        # Upcoming set of events with their trigger time
        self._events: list[tuple[datetime.datetime, CalendarEvent]] = []
        self._event_type = event_type

    async def async_attach(self) -> None:
        """Attach a calendar event listener."""
        now = dt_util.utcnow()
        await self._fetch_events(now)
        self._unsub_refresh = async_track_time_interval(
            self._hass, self._handle_refresh, UPDATE_INTERVAL
        )
        self._listen_next_calendar_event()

    @callback
    def async_detach(self) -> None:
        """Detach the calendar event listener."""
        self._clear_event_listener()
        if self._unsub_refresh:
            self._unsub_refresh()
        self._unsub_refresh = None

    async def _fetch_events(self, last_endtime: datetime.datetime) -> None:
        """Update the set of eligible events."""
        # Event time ranges are exclusive so the end time is expanded by 1sec
        end_time = last_endtime + UPDATE_INTERVAL + datetime.timedelta(seconds=1)
        _LOGGER.debug("Fetching events between %s, %s", last_endtime, end_time)
        events = await self._entity.async_get_events(self._hass, last_endtime, end_time)

        # Build list of events and the appropriate time to trigger an alarm. The
        # returned events may have already started but matched the start/end time
        # filtering above, so exclude any events that have already passed the
        # trigger time.
        event_list = []
        for event in events:
            event_time = (
                event.start_datetime_local
                if self._event_type == EVENT_START
                else event.end_datetime_local
            )
            if event_time > last_endtime:
                event_list.append((event_time, event))
        event_list.sort(key=lambda x: x[0])
        self._events = event_list
        _LOGGER.debug("Populated event list %s", self._events)

    @callback
    def _listen_next_calendar_event(self) -> None:
        """Set up the calendar event listener."""
        if not self._events:
            return

        (event_datetime, _event) = self._events[0]
        _LOGGER.debug("Scheduling next event trigger @ %s", event_datetime)
        self._unsub_event = async_track_point_in_utc_time(
            self._hass,
            self._handle_calendar_event,
            event_datetime,
        )

    def _clear_event_listener(self) -> None:
        """Reset the event listener."""
        if self._unsub_event:
            self._unsub_event()
        self._unsub_event = None

    async def _handle_calendar_event(self, now: datetime.datetime) -> None:
        """Handle calendar event."""
        _LOGGER.debug("Calendar event @ %s", now)
        self._dispatch_events(now)
        self._clear_event_listener()
        self._listen_next_calendar_event()

    def _dispatch_events(self, now: datetime.datetime) -> None:
        """Dispatch all events that are eligible to fire."""
        while self._events and self._events[0][0] <= now:
            (_fire_time, event) = self._events.pop(0)
            _LOGGER.debug("Event: %s", event)
            self._hass.async_run_hass_job(
                self._job,
                {"trigger": {**self._trigger_data, "calendar_event": event.as_dict()}},
            )

    async def _handle_refresh(self, now: datetime.datetime) -> None:
        """Handle core config update."""
        _LOGGER.debug("Refresh events @ %s", now)
        # Dispatch any eligible events in the boundary case where refresh
        # fires before the calendar event.
        self._dispatch_events(now)
        self._clear_event_listener()
        await self._fetch_events(now)
        self._listen_next_calendar_event()


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: AutomationActionType,
    automation_info: AutomationTriggerInfo,
) -> CALLBACK_TYPE:
    """Attach trigger for the specified calendar."""
    entity_id = config[CONF_ENTITY_ID]
    event_type = config[CONF_EVENT]

    component: EntityComponent = hass.data[DOMAIN]
    if not (entity := component.get_entity(entity_id)) or not isinstance(
        entity, CalendarEntity
    ):
        raise HomeAssistantError(
            f"Entity does not exist {entity_id} or is not a calendar entity"
        )

    trigger_data = {
        **automation_info["trigger_data"],
        "platform": DOMAIN,
        "event": event_type,
    }

    listener = CalendarEventListener(
        hass, HassJob(action), trigger_data, entity, event_type
    )
    await listener.async_attach()
    return listener.async_detach
