"""Reproduce an Fan state."""
from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
import logging
from typing import Any

from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import Context, HomeAssistant, State

from . import (
    ATTR_DIRECTION,
    ATTR_OSCILLATING,
    ATTR_PERCENTAGE,
    ATTR_PRESET_MODE,
    ATTR_SPEED,
    DOMAIN,
    SERVICE_OSCILLATE,
    SERVICE_SET_DIRECTION,
    SERVICE_SET_PERCENTAGE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_SPEED,
)

_LOGGER = logging.getLogger(__name__)

VALID_STATES = {STATE_ON, STATE_OFF}
ATTRIBUTES = {  # attribute: service
    ATTR_DIRECTION: SERVICE_SET_DIRECTION,
    ATTR_OSCILLATING: SERVICE_OSCILLATE,
    ATTR_SPEED: SERVICE_SET_SPEED,
    ATTR_PERCENTAGE: SERVICE_SET_PERCENTAGE,
    ATTR_PRESET_MODE: SERVICE_SET_PRESET_MODE,
}


async def _async_reproduce_state(
    hass: HomeAssistant,
    state: State,
    *,
    context: Context | None = None,
    reproduce_options: dict[str, Any] | None = None,
) -> None:
    """Reproduce a single state."""
    if (cur_state := hass.states.get(state.entity_id)) is None:
        _LOGGER.warning("Unable to find entity %s", state.entity_id)
        return

    if state.state not in VALID_STATES:
        _LOGGER.warning(
            "Invalid state specified for %s: %s", state.entity_id, state.state
        )
        return

    # Return if we are already at the right state.
    if cur_state.state == state.state and all(
        check_attr_equal(cur_state.attributes, state.attributes, attr)
        for attr in ATTRIBUTES
    ):
        return

    service_data = {ATTR_ENTITY_ID: state.entity_id}
    service_calls = {}  # service: service_data

    if state.state == STATE_ON:
        # The fan should be on
        if cur_state.state != STATE_ON:
            # Turn on the fan at first
            service_calls[SERVICE_TURN_ON] = service_data

        for attr, service in ATTRIBUTES.items():
            # Call services to adjust the attributes
            if attr in state.attributes and not check_attr_equal(
                state.attributes, cur_state.attributes, attr
            ):
                data = service_data.copy()
                data[attr] = state.attributes[attr]
                service_calls[service] = data

    elif state.state == STATE_OFF:
        service_calls[SERVICE_TURN_OFF] = service_data

    for service, data in service_calls.items():
        await hass.services.async_call(
            DOMAIN, service, data, context=context, blocking=True
        )


async def async_reproduce_states(
    hass: HomeAssistant,
    states: Iterable[State],
    *,
    context: Context | None = None,
    reproduce_options: dict[str, Any] | None = None,
) -> None:
    """Reproduce Fan states."""
    await asyncio.gather(
        *(
            _async_reproduce_state(
                hass, state, context=context, reproduce_options=reproduce_options
            )
            for state in states
        )
    )


def check_attr_equal(attr1: Mapping, attr2: Mapping, attr_str: str) -> bool:
    """Return true if the given attributes are equal."""
    return attr1.get(attr_str) == attr2.get(attr_str)
