"""The tests for the google calendar platform."""

from __future__ import annotations

import datetime
from http import HTTPStatus
from typing import Any
from unittest.mock import patch
import urllib

from aiohttp.client_exceptions import ClientError
import pytest

from homeassistant.components.google.const import DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON, Platform
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.template import DATE_STR_FORMAT
import homeassistant.util.dt as dt_util

from .conftest import (
    CALENDAR_ID,
    TEST_API_ENTITY,
    TEST_API_ENTITY_NAME,
    TEST_YAML_ENTITY,
    TEST_YAML_ENTITY_NAME,
)

from tests.common import async_fire_time_changed

TEST_ENTITY = TEST_API_ENTITY
TEST_ENTITY_NAME = TEST_API_ENTITY_NAME

TEST_EVENT = {
    "summary": "Test All Day Event",
    "start": {},
    "end": {},
    "location": "Test Cases",
    "description": "test event",
    "kind": "calendar#event",
    "created": "2016-06-23T16:37:57.000Z",
    "transparency": "transparent",
    "updated": "2016-06-24T01:57:21.045Z",
    "reminders": {"useDefault": True},
    "organizer": {
        "email": "uvrttabwegnui4gtia3vyqb@import.calendar.google.com",
        "displayName": "Organizer Name",
        "self": True,
    },
    "sequence": 0,
    "creator": {
        "email": "uvrttabwegnui4gtia3vyqb@import.calendar.google.com",
        "displayName": "Organizer Name",
        "self": True,
    },
    "id": "_c8rinwq863h45qnucyoi43ny8",
    "etag": '"2933466882090000"',
    "htmlLink": "https://www.google.com/calendar/event?eid=*******",
    "iCalUID": "cydrevtfuybguinhomj@google.com",
    "status": "confirmed",
}


@pytest.fixture(
    autouse=True, scope="module", params=["reader", "owner", "freeBusyReader"]
)
def calendar_access_role(request) -> str:
    """Fixture to exercise access roles in tests."""
    return request.param


@pytest.fixture(autouse=True)
def mock_test_setup(
    test_api_calendar,
    mock_calendars_list,
):
    """Fixture that sets up the default API responses during integration setup."""
    mock_calendars_list({"items": [test_api_calendar]})


def get_events_url(entity: str, start: str, end: str) -> str:
    """Create a url to get events during the specified time range."""
    return f"/api/calendars/{entity}?start={urllib.parse.quote(start)}&end={urllib.parse.quote(end)}"


def upcoming() -> dict[str, Any]:
    """Create a test event with an arbitrary start/end time fetched from the api url."""
    now = dt_util.now()
    return {
        "start": {"dateTime": now.isoformat()},
        "end": {"dateTime": (now + datetime.timedelta(minutes=5)).isoformat()},
    }


def upcoming_event_url(entity: str = TEST_ENTITY) -> str:
    """Return a calendar API to return events created by upcoming()."""
    now = dt_util.now()
    start = (now - datetime.timedelta(minutes=60)).isoformat()
    end = (now + datetime.timedelta(minutes=60)).isoformat()
    return get_events_url(entity, start, end)


async def test_all_day_event(hass, mock_events_list_items, component_setup):
    """Test that we can create an event trigger on device."""
    week_from_today = dt_util.now().date() + datetime.timedelta(days=7)
    end_event = week_from_today + datetime.timedelta(days=1)
    event = {
        **TEST_EVENT,
        "start": {"date": week_from_today.isoformat()},
        "end": {"date": end_event.isoformat()},
    }
    mock_events_list_items([event])

    assert await component_setup()

    state = hass.states.get(TEST_ENTITY)
    assert state.name == TEST_ENTITY_NAME
    assert state.state == STATE_OFF
    assert dict(state.attributes) == {
        "friendly_name": TEST_ENTITY_NAME,
        "message": event["summary"],
        "all_day": True,
        "offset_reached": False,
        "start_time": week_from_today.strftime(DATE_STR_FORMAT),
        "end_time": end_event.strftime(DATE_STR_FORMAT),
        "location": event["location"],
        "description": event["description"],
    }


async def test_future_event(hass, mock_events_list_items, component_setup):
    """Test that we can create an event trigger on device."""
    one_hour_from_now = dt_util.now() + datetime.timedelta(minutes=30)
    end_event = one_hour_from_now + datetime.timedelta(minutes=60)
    event = {
        **TEST_EVENT,
        "start": {"dateTime": one_hour_from_now.isoformat()},
        "end": {"dateTime": end_event.isoformat()},
    }
    mock_events_list_items([event])

    assert await component_setup()

    state = hass.states.get(TEST_ENTITY)
    assert state.name == TEST_ENTITY_NAME
    assert state.state == STATE_OFF
    assert dict(state.attributes) == {
        "friendly_name": TEST_ENTITY_NAME,
        "message": event["summary"],
        "all_day": False,
        "offset_reached": False,
        "start_time": one_hour_from_now.strftime(DATE_STR_FORMAT),
        "end_time": end_event.strftime(DATE_STR_FORMAT),
        "location": event["location"],
        "description": event["description"],
    }


async def test_in_progress_event(hass, mock_events_list_items, component_setup):
    """Test that we can create an event trigger on device."""
    middle_of_event = dt_util.now() - datetime.timedelta(minutes=30)
    end_event = middle_of_event + datetime.timedelta(minutes=60)
    event = {
        **TEST_EVENT,
        "start": {"dateTime": middle_of_event.isoformat()},
        "end": {"dateTime": end_event.isoformat()},
    }
    mock_events_list_items([event])

    assert await component_setup()

    state = hass.states.get(TEST_ENTITY)
    assert state.name == TEST_ENTITY_NAME
    assert state.state == STATE_ON
    assert dict(state.attributes) == {
        "friendly_name": TEST_ENTITY_NAME,
        "message": event["summary"],
        "all_day": False,
        "offset_reached": False,
        "start_time": middle_of_event.strftime(DATE_STR_FORMAT),
        "end_time": end_event.strftime(DATE_STR_FORMAT),
        "location": event["location"],
        "description": event["description"],
    }


async def test_offset_in_progress_event(hass, mock_events_list_items, component_setup):
    """Test that we can create an event trigger on device."""
    middle_of_event = dt_util.now() + datetime.timedelta(minutes=14)
    end_event = middle_of_event + datetime.timedelta(minutes=60)
    event_summary = "Test Event in Progress"
    event = {
        **TEST_EVENT,
        "start": {"dateTime": middle_of_event.isoformat()},
        "end": {"dateTime": end_event.isoformat()},
        "summary": f"{event_summary} !!-15",
    }
    mock_events_list_items([event])

    assert await component_setup()

    state = hass.states.get(TEST_ENTITY)
    assert state.name == TEST_ENTITY_NAME
    assert state.state == STATE_OFF
    assert dict(state.attributes) == {
        "friendly_name": TEST_ENTITY_NAME,
        "message": event_summary,
        "all_day": False,
        "offset_reached": True,
        "start_time": middle_of_event.strftime(DATE_STR_FORMAT),
        "end_time": end_event.strftime(DATE_STR_FORMAT),
        "location": event["location"],
        "description": event["description"],
    }


async def test_all_day_offset_in_progress_event(
    hass, mock_events_list_items, component_setup
):
    """Test that we can create an event trigger on device."""
    tomorrow = dt_util.now().date() + datetime.timedelta(days=1)
    end_event = tomorrow + datetime.timedelta(days=1)
    event_summary = "Test All Day Event Offset In Progress"
    event = {
        **TEST_EVENT,
        "start": {"date": tomorrow.isoformat()},
        "end": {"date": end_event.isoformat()},
        "summary": f"{event_summary} !!-25:0",
    }
    mock_events_list_items([event])

    assert await component_setup()

    state = hass.states.get(TEST_ENTITY)
    assert state.name == TEST_ENTITY_NAME
    assert state.state == STATE_OFF
    assert dict(state.attributes) == {
        "friendly_name": TEST_ENTITY_NAME,
        "message": event_summary,
        "all_day": True,
        "offset_reached": True,
        "start_time": tomorrow.strftime(DATE_STR_FORMAT),
        "end_time": end_event.strftime(DATE_STR_FORMAT),
        "location": event["location"],
        "description": event["description"],
    }


async def test_all_day_offset_event(hass, mock_events_list_items, component_setup):
    """Test that we can create an event trigger on device."""
    now = dt_util.now()
    day_after_tomorrow = now.date() + datetime.timedelta(days=2)
    end_event = day_after_tomorrow + datetime.timedelta(days=1)
    offset_hours = 1 + now.hour
    event_summary = "Test All Day Event Offset"
    event = {
        **TEST_EVENT,
        "start": {"date": day_after_tomorrow.isoformat()},
        "end": {"date": end_event.isoformat()},
        "summary": f"{event_summary} !!-{offset_hours}:0",
    }
    mock_events_list_items([event])

    assert await component_setup()

    state = hass.states.get(TEST_ENTITY)
    assert state.name == TEST_ENTITY_NAME
    assert state.state == STATE_OFF
    assert dict(state.attributes) == {
        "friendly_name": TEST_ENTITY_NAME,
        "message": event_summary,
        "all_day": True,
        "offset_reached": False,
        "start_time": day_after_tomorrow.strftime(DATE_STR_FORMAT),
        "end_time": end_event.strftime(DATE_STR_FORMAT),
        "location": event["location"],
        "description": event["description"],
    }


async def test_missing_summary(hass, mock_events_list_items, component_setup):
    """Test that we can create an event trigger on device."""
    start_event = dt_util.now() + datetime.timedelta(minutes=14)
    end_event = start_event + datetime.timedelta(minutes=60)
    event = {
        **TEST_EVENT,
        "start": {"dateTime": start_event.isoformat()},
        "end": {"dateTime": end_event.isoformat()},
    }
    del event["summary"]
    mock_events_list_items([event])

    assert await component_setup()

    state = hass.states.get(TEST_ENTITY)
    assert state.name == TEST_ENTITY_NAME
    assert state.state == STATE_OFF
    assert dict(state.attributes) == {
        "friendly_name": TEST_ENTITY_NAME,
        "message": "",
        "all_day": False,
        "offset_reached": False,
        "start_time": start_event.strftime(DATE_STR_FORMAT),
        "end_time": end_event.strftime(DATE_STR_FORMAT),
        "location": event["location"],
        "description": event["description"],
    }


async def test_update_error(
    hass,
    component_setup,
    mock_events_list,
    aioclient_mock,
):
    """Test that the calendar update handles a server error."""

    now = dt_util.now()
    mock_events_list(
        {
            "items": [
                {
                    **TEST_EVENT,
                    "start": {
                        "dateTime": (now + datetime.timedelta(minutes=-30)).isoformat()
                    },
                    "end": {
                        "dateTime": (now + datetime.timedelta(minutes=30)).isoformat()
                    },
                }
            ]
        }
    )
    assert await component_setup()

    state = hass.states.get(TEST_ENTITY)
    assert state.name == TEST_ENTITY_NAME
    assert state.state == "on"

    # Advance time to next data update interval
    now += datetime.timedelta(minutes=30)

    aioclient_mock.clear_requests()
    mock_events_list({}, exc=ClientError())

    with patch("homeassistant.util.utcnow", return_value=now):
        async_fire_time_changed(hass, now)
        await hass.async_block_till_done()

    # Entity is marked uanvailable due to API failure
    state = hass.states.get(TEST_ENTITY)
    assert state.name == TEST_ENTITY_NAME
    assert state.state == "unavailable"

    # Advance time past next coordinator update
    now += datetime.timedelta(minutes=30)

    aioclient_mock.clear_requests()
    mock_events_list(
        {
            "items": [
                {
                    **TEST_EVENT,
                    "start": {
                        "dateTime": (now + datetime.timedelta(minutes=30)).isoformat()
                    },
                    "end": {
                        "dateTime": (now + datetime.timedelta(minutes=60)).isoformat()
                    },
                }
            ]
        }
    )

    with patch("homeassistant.util.utcnow", return_value=now):
        async_fire_time_changed(hass, now)
        await hass.async_block_till_done()

    # State updated with new API response
    state = hass.states.get(TEST_ENTITY)
    assert state.name == TEST_ENTITY_NAME
    assert state.state == "off"


async def test_calendars_api(
    hass, hass_client, component_setup, mock_events_list_items
):
    """Test the Rest API returns the calendar."""
    mock_events_list_items([])
    assert await component_setup()

    client = await hass_client()
    response = await client.get("/api/calendars")
    assert response.status == HTTPStatus.OK
    data = await response.json()
    assert data == [
        {
            "entity_id": TEST_ENTITY,
            "name": TEST_ENTITY_NAME,
        }
    ]


async def test_http_event_api_failure(
    hass,
    hass_client,
    component_setup,
    mock_calendars_list,
    mock_events_list,
    aioclient_mock,
):
    """Test the Rest API response during a calendar failure."""
    mock_events_list({}, exc=ClientError())

    assert await component_setup()

    client = await hass_client()

    response = await client.get(upcoming_event_url())
    assert response.status == HTTPStatus.INTERNAL_SERVER_ERROR

    state = hass.states.get(TEST_ENTITY)
    assert state.name == TEST_ENTITY_NAME
    assert state.state == "unavailable"


@pytest.mark.freeze_time("2022-03-27 12:05:00+00:00")
async def test_http_api_event(
    hass, hass_client, mock_events_list_items, component_setup
):
    """Test querying the API and fetching events from the server."""
    hass.config.set_time_zone("Asia/Baghdad")
    event = {
        **TEST_EVENT,
        **upcoming(),
    }
    mock_events_list_items([event])
    assert await component_setup()

    client = await hass_client()
    response = await client.get(upcoming_event_url())
    assert response.status == HTTPStatus.OK
    events = await response.json()
    assert len(events) == 1
    assert {k: events[0].get(k) for k in ["summary", "start", "end"]} == {
        "summary": TEST_EVENT["summary"],
        "start": {"dateTime": "2022-03-27T15:05:00+03:00"},
        "end": {"dateTime": "2022-03-27T15:10:00+03:00"},
    }


@pytest.mark.freeze_time("2022-03-27 12:05:00+00:00")
async def test_http_api_all_day_event(
    hass, hass_client, mock_events_list_items, component_setup
):
    """Test querying the API and fetching events from the server."""
    event = {
        **TEST_EVENT,
        "start": {"date": "2022-03-27"},
        "end": {"date": "2022-03-28"},
    }
    mock_events_list_items([event])
    assert await component_setup()

    client = await hass_client()
    response = await client.get(upcoming_event_url())
    assert response.status == HTTPStatus.OK
    events = await response.json()
    assert len(events) == 1
    assert {k: events[0].get(k) for k in ["summary", "start", "end"]} == {
        "summary": TEST_EVENT["summary"],
        "start": {"date": "2022-03-27"},
        "end": {"date": "2022-03-28"},
    }


@pytest.mark.parametrize(
    "calendars_config_ignore_availability,transparency,expect_visible_event",
    [
        # Look at visibility to determine if entity is created
        (False, "opaque", True),
        (False, "transparent", False),
        # Ignoring availability and always show the entity
        (True, "opaque", True),
        (True, "transparency", True),
        # Default to ignore availability
        (None, "opaque", True),
        (None, "transparency", True),
    ],
)
async def test_opaque_event(
    hass,
    hass_client,
    mock_calendars_yaml,
    mock_events_list_items,
    component_setup,
    transparency,
    expect_visible_event,
):
    """Test querying the API and fetching events from the server."""
    event = {
        **TEST_EVENT,
        **upcoming(),
        "transparency": transparency,
    }
    mock_events_list_items([event])
    assert await component_setup()

    client = await hass_client()
    response = await client.get(upcoming_event_url(TEST_YAML_ENTITY))
    assert response.status == HTTPStatus.OK
    events = await response.json()
    assert (len(events) > 0) == expect_visible_event

    # Verify entity state for upcoming event
    state = hass.states.get(TEST_YAML_ENTITY)
    assert state.name == TEST_YAML_ENTITY_NAME
    assert state.state == (STATE_ON if expect_visible_event else STATE_OFF)


@pytest.mark.parametrize("mock_test_setup", [None])
async def test_scan_calendar_error(
    hass,
    component_setup,
    mock_calendars_list,
    config_entry,
):
    """Test that the calendar update handles a server error."""
    config_entry.add_to_hass(hass)
    mock_calendars_list({}, exc=ClientError())
    assert await component_setup()

    assert not hass.states.get(TEST_ENTITY)


async def test_future_event_update_behavior(
    hass, mock_events_list_items, component_setup
):
    """Test an future event that becomes active."""
    now = dt_util.now()
    now_utc = dt_util.utcnow()
    one_hour_from_now = now + datetime.timedelta(minutes=60)
    end_event = one_hour_from_now + datetime.timedelta(minutes=90)
    event = {
        **TEST_EVENT,
        "start": {"dateTime": one_hour_from_now.isoformat()},
        "end": {"dateTime": end_event.isoformat()},
    }
    mock_events_list_items([event])
    assert await component_setup()

    # Event has not started yet
    state = hass.states.get(TEST_ENTITY)
    assert state.name == TEST_ENTITY_NAME
    assert state.state == STATE_OFF

    # Advance time until event has started
    now += datetime.timedelta(minutes=60)
    now_utc += datetime.timedelta(minutes=60)
    with patch("homeassistant.util.dt.utcnow", return_value=now_utc), patch(
        "homeassistant.util.dt.now", return_value=now
    ):
        async_fire_time_changed(hass, now)
        await hass.async_block_till_done()

    # Event has started
    state = hass.states.get(TEST_ENTITY)
    assert state.state == STATE_ON


async def test_future_event_offset_update_behavior(
    hass, mock_events_list_items, component_setup
):
    """Test an future event that becomes active."""
    now = dt_util.now()
    now_utc = dt_util.utcnow()
    one_hour_from_now = now + datetime.timedelta(minutes=60)
    end_event = one_hour_from_now + datetime.timedelta(minutes=90)
    event_summary = "Test Event in Progress"
    event = {
        **TEST_EVENT,
        "start": {"dateTime": one_hour_from_now.isoformat()},
        "end": {"dateTime": end_event.isoformat()},
        "summary": f"{event_summary} !!-15",
    }
    mock_events_list_items([event])
    assert await component_setup()

    # Event has not started yet
    state = hass.states.get(TEST_ENTITY)
    assert state.name == TEST_ENTITY_NAME
    assert state.state == STATE_OFF
    assert not state.attributes["offset_reached"]

    # Advance time until event has started
    now += datetime.timedelta(minutes=45)
    now_utc += datetime.timedelta(minutes=45)
    with patch("homeassistant.util.dt.utcnow", return_value=now_utc), patch(
        "homeassistant.util.dt.now", return_value=now
    ):
        async_fire_time_changed(hass, now)
        await hass.async_block_till_done()

    # Event has not started, but the offset was reached
    state = hass.states.get(TEST_ENTITY)
    assert state.state == STATE_OFF
    assert state.attributes["offset_reached"]


async def test_unique_id(
    hass,
    mock_events_list_items,
    component_setup,
    config_entry,
):
    """Test entity is created with a unique id based on the config entry."""
    mock_events_list_items([])
    assert await component_setup()

    entity_registry = er.async_get(hass)
    registry_entries = er.async_entries_for_config_entry(
        entity_registry, config_entry.entry_id
    )
    assert {entry.unique_id for entry in registry_entries} == {
        f"{config_entry.unique_id}-{CALENDAR_ID}"
    }


@pytest.mark.parametrize(
    "old_unique_id", [CALENDAR_ID, f"{CALENDAR_ID}-we_are_we_are_a_test_calendar"]
)
async def test_unique_id_migration(
    hass,
    mock_events_list_items,
    component_setup,
    config_entry,
    old_unique_id,
):
    """Test that old unique id format is migrated to the new format that supports multiple accounts."""
    entity_registry = er.async_get(hass)

    # Create an entity using the old unique id format
    entity_registry.async_get_or_create(
        DOMAIN,
        Platform.CALENDAR,
        unique_id=old_unique_id,
        config_entry=config_entry,
    )
    registry_entries = er.async_entries_for_config_entry(
        entity_registry, config_entry.entry_id
    )
    assert {entry.unique_id for entry in registry_entries} == {old_unique_id}

    mock_events_list_items([])
    assert await component_setup()

    registry_entries = er.async_entries_for_config_entry(
        entity_registry, config_entry.entry_id
    )
    assert {entry.unique_id for entry in registry_entries} == {
        f"{config_entry.unique_id}-{CALENDAR_ID}"
    }


@pytest.mark.parametrize(
    "calendars_config",
    [
        [
            {
                "cal_id": CALENDAR_ID,
                "entities": [
                    {
                        "device_id": "backyard_light",
                        "name": "Backyard Light",
                        "search": "#Backyard",
                    },
                    {
                        "device_id": "front_light",
                        "name": "Front Light",
                        "search": "#Front",
                    },
                ],
            }
        ],
    ],
)
async def test_invalid_unique_id_cleanup(
    hass,
    mock_events_list_items,
    component_setup,
    config_entry,
    mock_calendars_yaml,
):
    """Test that old unique id format that is not actually unique is removed."""
    entity_registry = er.async_get(hass)

    # Create an entity using the old unique id format
    entity_registry.async_get_or_create(
        DOMAIN,
        Platform.CALENDAR,
        unique_id=f"{CALENDAR_ID}-backyard_light",
        config_entry=config_entry,
    )
    entity_registry.async_get_or_create(
        DOMAIN,
        Platform.CALENDAR,
        unique_id=f"{CALENDAR_ID}-front_light",
        config_entry=config_entry,
    )
    registry_entries = er.async_entries_for_config_entry(
        entity_registry, config_entry.entry_id
    )
    assert {entry.unique_id for entry in registry_entries} == {
        f"{CALENDAR_ID}-backyard_light",
        f"{CALENDAR_ID}-front_light",
    }

    mock_events_list_items([])
    assert await component_setup()

    registry_entries = er.async_entries_for_config_entry(
        entity_registry, config_entry.entry_id
    )
    assert not registry_entries


@pytest.mark.parametrize(
    "time_zone,event_order,calendar_access_role",
    # This only tests the reader role to force testing against the local
    # database filtering based on start/end time. (free busy reader would
    # just use the API response which this test is not exercising)
    [
        ("America/Los_Angeles", ["One", "Two", "All Day Event"], "reader"),
        ("America/Regina", ["One", "Two", "All Day Event"], "reader"),
        ("UTC", ["One", "All Day Event", "Two"], "reader"),
        ("Asia/Tokyo", ["All Day Event", "One", "Two"], "reader"),
    ],
)
async def test_all_day_iter_order(
    hass,
    hass_client,
    mock_events_list_items,
    component_setup,
    time_zone,
    event_order,
):
    """Test the sort order of an all day events depending on the time zone."""
    hass.config.set_time_zone(time_zone)
    mock_events_list_items(
        [
            {
                **TEST_EVENT,
                "id": "event-id-3",
                "summary": "All Day Event",
                "start": {"date": "2022-10-08"},
                "end": {"date": "2022-10-09"},
            },
            {
                **TEST_EVENT,
                "id": "event-id-1",
                "summary": "One",
                "start": {"dateTime": "2022-10-07T23:00:00+00:00"},
                "end": {"dateTime": "2022-10-07T23:30:00+00:00"},
            },
            {
                **TEST_EVENT,
                "id": "event-id-2",
                "summary": "Two",
                "start": {"dateTime": "2022-10-08T01:00:00+00:00"},
                "end": {"dateTime": "2022-10-08T02:00:00+00:00"},
            },
        ]
    )
    assert await component_setup()

    client = await hass_client()
    response = await client.get(
        get_events_url(TEST_ENTITY, "2022-10-06T00:00:00Z", "2022-10-09T00:00:00Z")
    )
    assert response.status == HTTPStatus.OK
    events = await response.json()
    assert [event["summary"] for event in events] == event_order
