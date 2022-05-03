"""Support for Google Calendar Search binary sensors."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta
import logging
from typing import Any

from gcal_sync.api import GoogleCalendarService, ListEventsRequest
from gcal_sync.exceptions import ApiException
from gcal_sync.model import Event

from homeassistant.components.calendar import (
    ENTITY_ID_FORMAT,
    CalendarEntity,
    CalendarEvent,
    extract_offset,
    is_offset_reached,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID, CONF_ENTITIES, CONF_NAME, CONF_OFFSET
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, PlatformNotReady
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import Throttle

from . import (
    CONF_CAL_ID,
    CONF_IGNORE_AVAILABILITY,
    CONF_SEARCH,
    CONF_TRACK,
    DATA_SERVICE,
    DEFAULT_CONF_OFFSET,
    DOMAIN,
    SERVICE_SCAN_CALENDARS,
)
from .const import DISCOVER_CALENDAR

_LOGGER = logging.getLogger(__name__)

DEFAULT_GOOGLE_SEARCH_PARAMS = {
    "orderBy": "startTime",
    "singleEvents": True,
}

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=15)

# Events have a transparency that determine whether or not they block time on calendar.
# When an event is opaque, it means "Show me as busy" which is the default.  Events that
# are not opaque are ignored by default.
TRANSPARENCY = "transparency"
OPAQUE = "opaque"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the google calendar platform."""

    @callback
    def async_discover(discovery_info: dict[str, Any]) -> None:
        _async_setup_entities(
            hass,
            entry,
            async_add_entities,
            discovery_info,
        )

    entry.async_on_unload(
        async_dispatcher_connect(hass, DISCOVER_CALENDAR, async_discover)
    )

    # Look for any new calendars
    try:
        await hass.services.async_call(DOMAIN, SERVICE_SCAN_CALENDARS, blocking=True)
    except HomeAssistantError as err:
        # This can happen if there's a connection error during setup.
        raise PlatformNotReady(str(err)) from err


@callback
def _async_setup_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    disc_info: dict[str, Any],
) -> None:
    calendar_service = hass.data[DOMAIN][DATA_SERVICE]
    entities = []
    for data in disc_info[CONF_ENTITIES]:
        if not data[CONF_TRACK]:
            continue
        entity_id = generate_entity_id(
            ENTITY_ID_FORMAT, data[CONF_DEVICE_ID], hass=hass
        )
        entity = GoogleCalendarEntity(
            calendar_service, disc_info[CONF_CAL_ID], data, entity_id
        )
        entities.append(entity)

    async_add_entities(entities, True)


class GoogleCalendarEntity(CalendarEntity):
    """A calendar event device."""

    def __init__(
        self,
        calendar_service: GoogleCalendarService,
        calendar_id: str,
        data: dict[str, Any],
        entity_id: str,
    ) -> None:
        """Create the Calendar event device."""
        self._calendar_service = calendar_service
        self._calendar_id = calendar_id
        self._search: str | None = data.get(CONF_SEARCH)
        self._ignore_availability: bool = data.get(CONF_IGNORE_AVAILABILITY, False)
        self._event: CalendarEvent | None = None
        self._name: str = data[CONF_NAME]
        self._offset = data.get(CONF_OFFSET, DEFAULT_CONF_OFFSET)
        self._offset_value: timedelta | None = None
        self.entity_id = entity_id

    @property
    def extra_state_attributes(self) -> dict[str, bool]:
        """Return the device state attributes."""
        return {"offset_reached": self.offset_reached}

    @property
    def offset_reached(self) -> bool:
        """Return whether or not the event offset was reached."""
        if self._event and self._offset_value:
            return is_offset_reached(
                self._event.start_datetime_local, self._offset_value
            )
        return False

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        return self._event

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    def _event_filter(self, event: Event) -> bool:
        """Return True if the event is visible."""
        if self._ignore_availability:
            return True
        return event.transparency == OPAQUE

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Get all events in a specific time frame."""

        request = ListEventsRequest(
            calendar_id=self._calendar_id,
            start_time=start_date,
            end_time=end_date,
            search=self._search,
        )
        result_items = []
        try:
            result = await self._calendar_service.async_list_events(request)
            async for result_page in result:
                result_items.extend(result_page.items)
        except ApiException as err:
            _LOGGER.error("Unable to connect to Google: %s", err)
            return []
        return [
            _get_calendar_event(event)
            for event in filter(self._event_filter, result_items)
        ]

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self) -> None:
        """Get the latest data."""
        request = ListEventsRequest(calendar_id=self._calendar_id, search=self._search)
        try:
            result = await self._calendar_service.async_list_events(request)
        except ApiException as err:
            _LOGGER.error("Unable to connect to Google: %s", err)
            return

        # Pick the first visible event and apply offset calculations.
        valid_items = filter(self._event_filter, result.items)
        event = copy.deepcopy(next(valid_items, None))
        if event:
            (event.summary, offset) = extract_offset(event.summary, self._offset)
            self._event = _get_calendar_event(event)
            self._offset_value = offset
        else:
            self._event = None


def _get_calendar_event(event: Event) -> CalendarEvent:
    """Return a CalendarEvent from an API event."""
    return CalendarEvent(
        summary=event.summary,
        start=event.start.value,
        end=event.end.value,
        description=event.description,
        location=event.location,
    )
