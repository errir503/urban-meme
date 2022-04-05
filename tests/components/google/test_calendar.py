"""The tests for the google calendar platform."""

from __future__ import annotations

import datetime
from http import HTTPStatus
from typing import Any
from unittest.mock import patch
import urllib

import httplib2
import pytest

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.helpers.template import DATE_STR_FORMAT
import homeassistant.util.dt as dt_util

from .conftest import TEST_YAML_ENTITY, TEST_YAML_ENTITY_NAME

from tests.common import async_fire_time_changed

TEST_ENTITY = TEST_YAML_ENTITY
TEST_ENTITY_NAME = TEST_YAML_ENTITY_NAME

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


@pytest.fixture(autouse=True)
def mock_test_setup(
    hass,
    mock_calendars_yaml,
    test_api_calendar,
    mock_calendars_list,
    config_entry,
):
    """Fixture that pulls in the default fixtures for tests in this file."""
    mock_calendars_list({"items": [test_api_calendar]})
    config_entry.add_to_hass(hass)
    return


def upcoming() -> dict[str, Any]:
    """Create a test event with an arbitrary start/end time fetched from the api url."""
    now = dt_util.now()
    return {
        "start": {"dateTime": now.isoformat()},
        "end": {"dateTime": (now + datetime.timedelta(minutes=5)).isoformat()},
    }


def upcoming_date() -> dict[str, Any]:
    """Create a test event with an arbitrary start/end date fetched from the api url."""
    now = dt_util.now()
    return {
        "start": {"date": now.date().isoformat()},
        "end": {"date": now.date().isoformat()},
    }


def upcoming_event_url() -> str:
    """Return a calendar API to return events created by upcoming()."""
    now = dt_util.now()
    start = (now - datetime.timedelta(minutes=60)).isoformat()
    end = (now + datetime.timedelta(minutes=60)).isoformat()
    return f"/api/calendars/{TEST_ENTITY}?start={urllib.parse.quote(start)}&end={urllib.parse.quote(end)}"


async def test_all_day_event(
    hass, mock_events_list_items, mock_token_read, component_setup
):
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


async def test_update_error(
    hass, calendar_resource, component_setup, test_api_calendar
):
    """Test that the calendar update handles a server error."""

    now = dt_util.now()
    with patch("homeassistant.components.google.api.google_discovery.build") as mock:
        mock.return_value.calendarList.return_value.list.return_value.execute.return_value = {
            "items": [test_api_calendar]
        }
        mock.return_value.events.return_value.list.return_value.execute.return_value = {
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
        assert await component_setup()

    state = hass.states.get(TEST_ENTITY)
    assert state.name == TEST_ENTITY_NAME
    assert state.state == "on"

    # Advance time to avoid throttling
    now += datetime.timedelta(minutes=30)
    with patch(
        "homeassistant.components.google.api.google_discovery.build",
        side_effect=httplib2.ServerNotFoundError("unit test"),
    ), patch("homeassistant.util.utcnow", return_value=now):
        async_fire_time_changed(hass, now)
        await hass.async_block_till_done()

    # No change
    state = hass.states.get(TEST_ENTITY)
    assert state.name == TEST_ENTITY_NAME
    assert state.state == "on"

    # Advance time beyond update/throttle point
    now += datetime.timedelta(minutes=30)
    with patch(
        "homeassistant.components.google.api.google_discovery.build"
    ) as mock, patch("homeassistant.util.utcnow", return_value=now):
        mock.return_value.events.return_value.list.return_value.execute.return_value = {
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
        async_fire_time_changed(hass, now)
        await hass.async_block_till_done()

    # State updated
    state = hass.states.get(TEST_ENTITY)
    assert state.name == TEST_ENTITY_NAME
    assert state.state == "off"


async def test_calendars_api(hass, hass_client, component_setup):
    """Test the Rest API returns the calendar."""
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
    hass, hass_client, calendar_resource, component_setup
):
    """Test the Rest API response during a calendar failure."""
    assert await component_setup()

    client = await hass_client()

    calendar_resource.side_effect = httplib2.ServerNotFoundError("unit test")

    response = await client.get(upcoming_event_url())
    assert response.status == HTTPStatus.OK
    # A failure to talk to the server results in an empty list of events
    events = await response.json()
    assert events == []


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
        **upcoming_date(),
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
        "end": {"date": "2022-03-27"},
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
    response = await client.get(upcoming_event_url())
    assert response.status == HTTPStatus.OK
    events = await response.json()
    assert (len(events) > 0) == expect_visible_event


async def test_scan_calendar_error(
    hass,
    calendar_resource,
    component_setup,
    test_api_calendar,
):
    """Test that the calendar update handles a server error."""
    with patch(
        "homeassistant.components.google.api.google_discovery.build",
        side_effect=httplib2.ServerNotFoundError("unit test"),
    ):
        assert await component_setup()

    assert not hass.states.get(TEST_ENTITY)
