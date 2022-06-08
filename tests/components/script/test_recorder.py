"""The tests for script recorder."""
from __future__ import annotations

import pytest

from homeassistant.components import script
from homeassistant.components.recorder.db_schema import StateAttributes, States
from homeassistant.components.recorder.util import session_scope
from homeassistant.components.script import (
    ATTR_CUR,
    ATTR_LAST_ACTION,
    ATTR_LAST_TRIGGERED,
    ATTR_MAX,
    ATTR_MODE,
)
from homeassistant.const import ATTR_FRIENDLY_NAME
from homeassistant.core import Context, State, callback
from homeassistant.setup import async_setup_component

from tests.common import async_mock_service
from tests.components.recorder.common import async_wait_recording_done


@pytest.fixture
def calls(hass):
    """Track calls to a mock service."""
    return async_mock_service(hass, "test", "automation")


async def test_exclude_attributes(hass, recorder_mock, calls):
    """Test automation registered attributes to be excluded."""
    await hass.async_block_till_done()
    calls = []
    context = Context()

    @callback
    def record_call(service):
        """Add recorded event to set."""
        calls.append(service)

    hass.services.async_register("test", "script", record_call)

    assert await async_setup_component(
        hass,
        "script",
        {
            "script": {
                "test": {
                    "sequence": {
                        "service": "test.script",
                        "data_template": {"hello": "{{ greeting }}"},
                    }
                }
            }
        },
    )

    await hass.services.async_call(
        script.DOMAIN, "test", {"greeting": "world"}, context=context
    )
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)
    assert len(calls) == 1

    def _fetch_states() -> list[State]:
        with session_scope(hass=hass) as session:
            native_states = []
            for db_state, db_state_attributes in session.query(States, StateAttributes):
                state = db_state.to_native()
                state.attributes = db_state_attributes.to_native()
                native_states.append(state)
            return native_states

    states: list[State] = await hass.async_add_executor_job(_fetch_states)
    assert len(states) > 1
    for state in states:
        assert ATTR_LAST_TRIGGERED not in state.attributes
        assert ATTR_MODE not in state.attributes
        assert ATTR_CUR not in state.attributes
        assert ATTR_LAST_ACTION not in state.attributes
        assert ATTR_MAX not in state.attributes
        assert ATTR_FRIENDLY_NAME in state.attributes
