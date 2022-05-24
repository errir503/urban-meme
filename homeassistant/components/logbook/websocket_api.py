"""Event parser and human readable log generator."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime as dt, timedelta
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.recorder import get_instance
from homeassistant.components.websocket_api import messages
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.const import JSON_DUMP
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
import homeassistant.util.dt as dt_util

from .helpers import (
    async_determine_event_types,
    async_filter_entities,
    async_subscribe_events,
)
from .models import async_event_to_row
from .processor import EventProcessor

MAX_PENDING_LOGBOOK_EVENTS = 2048
EVENT_COALESCE_TIME = 0.5
MAX_RECORDER_WAIT = 10

_LOGGER = logging.getLogger(__name__)


@callback
def async_setup(hass: HomeAssistant) -> None:
    """Set up the logbook websocket API."""
    websocket_api.async_register_command(hass, ws_get_events)
    websocket_api.async_register_command(hass, ws_event_stream)


async def _async_get_ws_formatted_events(
    hass: HomeAssistant,
    msg_id: int,
    start_time: dt,
    end_time: dt,
    formatter: Callable[[int, Any], dict[str, Any]],
    event_processor: EventProcessor,
) -> tuple[str, dt | None]:
    """Async wrapper around _ws_formatted_get_events."""
    return await get_instance(hass).async_add_executor_job(
        _ws_formatted_get_events,
        msg_id,
        start_time,
        end_time,
        formatter,
        event_processor,
    )


def _ws_formatted_get_events(
    msg_id: int,
    start_day: dt,
    end_day: dt,
    formatter: Callable[[int, Any], dict[str, Any]],
    event_processor: EventProcessor,
) -> tuple[str, dt | None]:
    """Fetch events and convert them to json in the executor."""
    events = event_processor.get_events(start_day, end_day)
    last_time = None
    if events:
        last_time = dt_util.utc_from_timestamp(events[-1]["when"])
    result = formatter(msg_id, events)
    return JSON_DUMP(result), last_time


async def _async_events_consumer(
    setup_complete_future: asyncio.Future[dt],
    connection: ActiveConnection,
    msg_id: int,
    stream_queue: asyncio.Queue[Event],
    event_processor: EventProcessor,
) -> None:
    """Stream events from the queue."""
    subscriptions_setup_complete_time = await setup_complete_future
    event_processor.switch_to_live()

    while True:
        events: list[Event] = [await stream_queue.get()]
        # If the event is older than the last db
        # event we already sent it so we skip it.
        if events[0].time_fired <= subscriptions_setup_complete_time:
            continue
        # We sleep for the EVENT_COALESCE_TIME so
        # we can group events together to minimize
        # the number of websocket messages when the
        # system is overloaded with an event storm
        await asyncio.sleep(EVENT_COALESCE_TIME)
        while not stream_queue.empty():
            events.append(stream_queue.get_nowait())

        if logbook_events := event_processor.humanify(
            async_event_to_row(e) for e in events
        ):
            connection.send_message(
                JSON_DUMP(
                    messages.event_message(
                        msg_id,
                        logbook_events,
                    )
                )
            )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "logbook/event_stream",
        vol.Required("start_time"): str,
        vol.Optional("entity_ids"): [str],
        vol.Optional("device_ids"): [str],
    }
)
@websocket_api.async_response
async def ws_event_stream(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Handle logbook stream events websocket command."""
    start_time_str = msg["start_time"]
    utc_now = dt_util.utcnow()

    if start_time := dt_util.parse_datetime(start_time_str):
        start_time = dt_util.as_utc(start_time)

    if not start_time or start_time > utc_now:
        connection.send_error(msg["id"], "invalid_start_time", "Invalid start_time")
        return

    device_ids = msg.get("device_ids")
    entity_ids = msg.get("entity_ids")
    if entity_ids:
        entity_ids = async_filter_entities(hass, entity_ids)
    event_types = async_determine_event_types(hass, entity_ids, device_ids)

    event_processor = EventProcessor(
        hass,
        event_types,
        entity_ids,
        device_ids,
        None,
        timestamp=True,
        include_entity_name=False,
    )

    stream_queue: asyncio.Queue[Event] = asyncio.Queue(MAX_PENDING_LOGBOOK_EVENTS)
    subscriptions: list[CALLBACK_TYPE] = []
    setup_complete_future: asyncio.Future[dt] = asyncio.Future()
    task = asyncio.create_task(
        _async_events_consumer(
            setup_complete_future,
            connection,
            msg["id"],
            stream_queue,
            event_processor,
        )
    )

    def _unsub() -> None:
        """Unsubscribe from all events."""
        for subscription in subscriptions:
            subscription()
        subscriptions.clear()
        if task:
            task.cancel()

    @callback
    def _queue_or_cancel(event: Event) -> None:
        """Queue an event to be processed or cancel."""
        try:
            stream_queue.put_nowait(event)
        except asyncio.QueueFull:
            _LOGGER.debug(
                "Client exceeded max pending messages of %s",
                MAX_PENDING_LOGBOOK_EVENTS,
            )
            _unsub()

    async_subscribe_events(
        hass, subscriptions, _queue_or_cancel, event_types, entity_ids, device_ids
    )
    subscriptions_setup_complete_time = dt_util.utcnow()
    connection.subscriptions[msg["id"]] = _unsub
    connection.send_result(msg["id"])

    # Fetch everything from history
    message, last_event_time = await _async_get_ws_formatted_events(
        hass,
        msg["id"],
        start_time,
        subscriptions_setup_complete_time,
        messages.event_message,
        event_processor,
    )
    # If there is no last_time there are no historical
    # results, but we still send an empty message so
    # consumers of the api know their request was
    # answered but there were no results
    connection.send_message(message)
    try:
        await asyncio.wait_for(
            get_instance(hass).async_block_till_done(), MAX_RECORDER_WAIT
        )
    except asyncio.TimeoutError:
        _LOGGER.debug(
            "Recorder is behind more than %s seconds, starting live stream; Some results may be missing"
        )

    if setup_complete_future.cancelled():
        # Unsubscribe happened while waiting for recorder
        return

    #
    # Fetch any events from the database that have
    # not been committed since the original fetch
    # so we can switch over to using the subscriptions
    #
    # We only want events that happened after the last event
    # we had from the last database query or the maximum
    # time we allow the recorder to be behind
    #
    max_recorder_behind = subscriptions_setup_complete_time - timedelta(
        seconds=MAX_RECORDER_WAIT
    )
    second_fetch_start_time = max(
        last_event_time or max_recorder_behind, max_recorder_behind
    )
    message, final_cutoff_time = await _async_get_ws_formatted_events(
        hass,
        msg["id"],
        second_fetch_start_time,
        subscriptions_setup_complete_time,
        messages.event_message,
        event_processor,
    )
    if final_cutoff_time:  # Only sends results if we have them
        connection.send_message(message)

    if not setup_complete_future.cancelled():
        # Unsubscribe happened while waiting for formatted events
        setup_complete_future.set_result(subscriptions_setup_complete_time)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "logbook/get_events",
        vol.Required("start_time"): str,
        vol.Optional("end_time"): str,
        vol.Optional("entity_ids"): [str],
        vol.Optional("device_ids"): [str],
        vol.Optional("context_id"): str,
    }
)
@websocket_api.async_response
async def ws_get_events(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Handle logbook get events websocket command."""
    start_time_str = msg["start_time"]
    end_time_str = msg.get("end_time")
    utc_now = dt_util.utcnow()

    if start_time := dt_util.parse_datetime(start_time_str):
        start_time = dt_util.as_utc(start_time)
    else:
        connection.send_error(msg["id"], "invalid_start_time", "Invalid start_time")
        return

    if not end_time_str:
        end_time = utc_now
    elif parsed_end_time := dt_util.parse_datetime(end_time_str):
        end_time = dt_util.as_utc(parsed_end_time)
    else:
        connection.send_error(msg["id"], "invalid_end_time", "Invalid end_time")
        return

    if start_time > utc_now:
        connection.send_result(msg["id"], [])
        return

    device_ids = msg.get("device_ids")
    entity_ids = msg.get("entity_ids")
    context_id = msg.get("context_id")
    if entity_ids:
        entity_ids = async_filter_entities(hass, entity_ids)
        if not entity_ids and not device_ids:
            # Everything has been filtered away
            connection.send_result(msg["id"], [])
            return

    event_types = async_determine_event_types(hass, entity_ids, device_ids)

    event_processor = EventProcessor(
        hass,
        event_types,
        entity_ids,
        device_ids,
        context_id,
        timestamp=True,
        include_entity_name=False,
    )

    message, _ = await _async_get_ws_formatted_events(
        hass,
        msg["id"],
        start_time,
        end_time,
        messages.result_message,
        event_processor,
    )
    connection.send_message(message)
