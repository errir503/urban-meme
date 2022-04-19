"""The tests for recorder platform."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.components.input_select import ATTR_OPTIONS, DOMAIN
from homeassistant.components.recorder.models import StateAttributes, States
from homeassistant.components.recorder.util import session_scope
from homeassistant.const import ATTR_EDITABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from tests.common import async_fire_time_changed, async_init_recorder_component
from tests.components.recorder.common import async_wait_recording_done_without_instance


async def test_exclude_attributes(
    hass: HomeAssistant, enable_custom_integrations: None
):
    """Test attributes to be excluded."""
    await async_init_recorder_component(hass)
    assert await async_setup_component(
        hass,
        DOMAIN,
        {
            DOMAIN: {
                "test": {
                    "options": ["first option", "middle option", "last option"],
                    "initial": "middle option",
                }
            }
        },
    )

    state = hass.states.get("input_select.test")
    assert state
    assert state.attributes[ATTR_EDITABLE] is False

    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=5))
    await hass.async_block_till_done()
    await async_wait_recording_done_without_instance(hass)

    def _fetch_states() -> list[State]:
        with session_scope(hass=hass) as session:
            native_states = []
            for db_state, db_state_attributes in session.query(States, StateAttributes):
                state = db_state.to_native()
                state.attributes = db_state_attributes.to_native()
                native_states.append(state)
            return native_states

    states: list[State] = await hass.async_add_executor_job(_fetch_states)
    assert len(states) == 1
    assert ATTR_EDITABLE not in states[0].attributes
    assert ATTR_OPTIONS in states[0].attributes
