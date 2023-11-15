"""Message templates for websocket commands."""
from __future__ import annotations

from functools import lru_cache
import logging
from typing import TYPE_CHECKING, Any, Final, cast

import voluptuous as vol

from homeassistant.const import (
    COMPRESSED_STATE_ATTRIBUTES,
    COMPRESSED_STATE_CONTEXT,
    COMPRESSED_STATE_LAST_CHANGED,
    COMPRESSED_STATE_LAST_UPDATED,
    COMPRESSED_STATE_STATE,
)
from homeassistant.core import Event, State
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.json import JSON_DUMP, find_paths_unserializable_data
from homeassistant.util.json import format_unserializable_data

from . import const

_LOGGER: Final = logging.getLogger(__name__)

# Minimal requirements of a message
MINIMAL_MESSAGE_SCHEMA: Final = vol.Schema(
    {vol.Required("id"): cv.positive_int, vol.Required("type"): cv.string},
    extra=vol.ALLOW_EXTRA,
)

# Base schema to extend by message handlers
BASE_COMMAND_MESSAGE_SCHEMA: Final = vol.Schema({vol.Required("id"): cv.positive_int})

STATE_DIFF_ADDITIONS = "+"
STATE_DIFF_REMOVALS = "-"

ENTITY_EVENT_ADD = "a"
ENTITY_EVENT_REMOVE = "r"
ENTITY_EVENT_CHANGE = "c"

BASE_ERROR_MESSAGE = {
    "type": const.TYPE_RESULT,
    "success": False,
}

INVALID_JSON_PARTIAL_MESSAGE = JSON_DUMP(
    {
        **BASE_ERROR_MESSAGE,
        "error": {
            "code": const.ERR_UNKNOWN_ERROR,
            "message": "Invalid JSON in response",
        },
    }
)


def result_message(iden: int, result: Any = None) -> dict[str, Any]:
    """Return a success result message."""
    return {"id": iden, "type": const.TYPE_RESULT, "success": True, "result": result}


def construct_result_message(iden: int, payload: str) -> str:
    """Construct a success result message JSON."""
    return f'{{"id":{iden},"type":"result","success":true,"result":{payload}}}'


def error_message(
    iden: int | None,
    code: str,
    message: str,
    translation_key: str | None = None,
    translation_domain: str | None = None,
    translation_placeholders: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return an error result message."""
    error_payload: dict[str, Any] = {
        "code": code,
        "message": message,
    }
    # In case `translation_key` is `None` we do not set it, nor the
    # `translation`_placeholders` and `translation_domain`.
    if translation_key is not None:
        error_payload["translation_key"] = translation_key
        error_payload["translation_placeholders"] = translation_placeholders
        error_payload["translation_domain"] = translation_domain
    return {
        "id": iden,
        **BASE_ERROR_MESSAGE,
        "error": error_payload,
    }


def event_message(iden: int, event: Any) -> dict[str, Any]:
    """Return an event message."""
    return {"id": iden, "type": "event", "event": event}


def cached_event_message(iden: int, event: Event) -> str:
    """Return an event message.

    Serialize to json once per message.

    Since we can have many clients connected that are
    all getting many of the same events (mostly state changed)
    we can avoid serializing the same data for each connection.
    """
    return f'{_partial_cached_event_message(event)[:-1]},"id":{iden}}}'


@lru_cache(maxsize=128)
def _partial_cached_event_message(event: Event) -> str:
    """Cache and serialize the event to json.

    The message is constructed without the id which appended
    in cached_event_message.
    """
    return (
        _message_to_json_or_none({"type": "event", "event": event.as_dict()})
        or INVALID_JSON_PARTIAL_MESSAGE
    )


def cached_state_diff_message(iden: int, event: Event) -> str:
    """Return an event message.

    Serialize to json once per message.

    Since we can have many clients connected that are
    all getting many of the same events (mostly state changed)
    we can avoid serializing the same data for each connection.
    """
    return f'{_partial_cached_state_diff_message(event)[:-1]},"id":{iden}}}'


@lru_cache(maxsize=128)
def _partial_cached_state_diff_message(event: Event) -> str:
    """Cache and serialize the event to json.

    The message is constructed without the id which
    will be appended in cached_state_diff_message
    """
    return (
        _message_to_json_or_none({"type": "event", "event": _state_diff_event(event)})
        or INVALID_JSON_PARTIAL_MESSAGE
    )


def _state_diff_event(event: Event) -> dict:
    """Convert a state_changed event to the minimal version.

    State update example

    {
        "a": {entity_id: compressed_state,…}
        "c": {entity_id: diff,…}
        "r": [entity_id,…]
    }
    """
    if (event_new_state := event.data["new_state"]) is None:
        return {ENTITY_EVENT_REMOVE: [event.data["entity_id"]]}
    if TYPE_CHECKING:
        event_new_state = cast(State, event_new_state)
    if (event_old_state := event.data["old_state"]) is None:
        return {
            ENTITY_EVENT_ADD: {
                event_new_state.entity_id: event_new_state.as_compressed_state
            }
        }
    if TYPE_CHECKING:
        event_old_state = cast(State, event_old_state)
    return _state_diff(event_old_state, event_new_state)


def _state_diff(
    old_state: State, new_state: State
) -> dict[str, dict[str, dict[str, dict[str, str | list[str]]]]]:
    """Create a diff dict that can be used to overlay changes."""
    additions: dict[str, Any] = {}
    diff: dict[str, dict[str, Any]] = {STATE_DIFF_ADDITIONS: additions}
    new_state_context = new_state.context
    old_state_context = old_state.context
    if old_state.state != new_state.state:
        additions[COMPRESSED_STATE_STATE] = new_state.state
    if old_state.last_changed != new_state.last_changed:
        additions[COMPRESSED_STATE_LAST_CHANGED] = new_state.last_changed.timestamp()
    elif old_state.last_updated != new_state.last_updated:
        additions[COMPRESSED_STATE_LAST_UPDATED] = new_state.last_updated.timestamp()
    if old_state_context.parent_id != new_state_context.parent_id:
        additions[COMPRESSED_STATE_CONTEXT] = {"parent_id": new_state_context.parent_id}
    if old_state_context.user_id != new_state_context.user_id:
        if COMPRESSED_STATE_CONTEXT in additions:
            additions[COMPRESSED_STATE_CONTEXT]["user_id"] = new_state_context.user_id
        else:
            additions[COMPRESSED_STATE_CONTEXT] = {"user_id": new_state_context.user_id}
    if old_state_context.id != new_state_context.id:
        if COMPRESSED_STATE_CONTEXT in additions:
            additions[COMPRESSED_STATE_CONTEXT]["id"] = new_state_context.id
        else:
            additions[COMPRESSED_STATE_CONTEXT] = new_state_context.id
    if (old_attributes := old_state.attributes) != (
        new_attributes := new_state.attributes
    ):
        for key, value in new_attributes.items():
            if old_attributes.get(key) != value:
                additions.setdefault(COMPRESSED_STATE_ATTRIBUTES, {})[key] = value
        if removed := set(old_attributes).difference(new_attributes):
            # sets are not JSON serializable by default so we convert to list
            # here if there are any values to avoid jumping into the json_encoder_default
            # for every state diff with a removed attribute
            diff[STATE_DIFF_REMOVALS] = {COMPRESSED_STATE_ATTRIBUTES: list(removed)}
    return {ENTITY_EVENT_CHANGE: {new_state.entity_id: diff}}


def _message_to_json_or_none(message: dict[str, Any]) -> str | None:
    """Serialize a websocket message to json or return None."""
    try:
        return JSON_DUMP(message)
    except (ValueError, TypeError):
        _LOGGER.error(
            "Unable to serialize to JSON. Bad data found at %s",
            format_unserializable_data(
                find_paths_unserializable_data(message, dump=JSON_DUMP)
            ),
        )
    return None


def message_to_json(message: dict[str, Any]) -> str:
    """Serialize a websocket message to json or return an error."""
    return _message_to_json_or_none(message) or JSON_DUMP(
        error_message(
            message["id"], const.ERR_UNKNOWN_ERROR, "Invalid JSON in response"
        )
    )
