"""The tests for the Restore component."""
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import patch

from homeassistant.const import EVENT_HOMEASSISTANT_START, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CoreState, HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.restore_state import (
    DATA_RESTORE_STATE_TASK,
    STORAGE_KEY,
    RestoreEntity,
    RestoreStateData,
    StoredState,
)
from homeassistant.util import dt as dt_util

from tests.common import async_fire_time_changed


async def test_caching_data(hass: HomeAssistant) -> None:
    """Test that we cache data."""
    now = dt_util.utcnow()
    stored_states = [
        StoredState(State("input_boolean.b0", "on"), None, now),
        StoredState(State("input_boolean.b1", "on"), None, now),
        StoredState(State("input_boolean.b2", "on"), None, now),
    ]

    data = await RestoreStateData.async_get_instance(hass)
    await hass.async_block_till_done()
    await data.store.async_save([state.as_dict() for state in stored_states])

    # Emulate a fresh load
    hass.data.pop(DATA_RESTORE_STATE_TASK)

    entity = RestoreEntity()
    entity.hass = hass
    entity.entity_id = "input_boolean.b1"

    # Mock that only b1 is present this run
    with patch(
        "homeassistant.helpers.restore_state.Store.async_save"
    ) as mock_write_data:
        state = await entity.async_get_last_state()
        await hass.async_block_till_done()

    assert state is not None
    assert state.entity_id == "input_boolean.b1"
    assert state.state == "on"

    assert mock_write_data.called


async def test_periodic_write(hass: HomeAssistant) -> None:
    """Test that we write periodiclly but not after stop."""
    data = await RestoreStateData.async_get_instance(hass)
    await hass.async_block_till_done()
    await data.store.async_save([])

    # Emulate a fresh load
    hass.data.pop(DATA_RESTORE_STATE_TASK)

    entity = RestoreEntity()
    entity.hass = hass
    entity.entity_id = "input_boolean.b1"

    with patch(
        "homeassistant.helpers.restore_state.Store.async_save"
    ) as mock_write_data:
        await entity.async_get_last_state()
        await hass.async_block_till_done()

    assert mock_write_data.called

    with patch(
        "homeassistant.helpers.restore_state.Store.async_save"
    ) as mock_write_data:
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=15))
        await hass.async_block_till_done()

    assert mock_write_data.called

    with patch(
        "homeassistant.helpers.restore_state.Store.async_save"
    ) as mock_write_data:
        hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
        await hass.async_block_till_done()

    assert mock_write_data.called

    with patch(
        "homeassistant.helpers.restore_state.Store.async_save"
    ) as mock_write_data:
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=30))
        await hass.async_block_till_done()

    assert not mock_write_data.called


async def test_save_persistent_states(hass: HomeAssistant) -> None:
    """Test that we cancel the currently running job, save the data, and verify the perdiodic job continues."""
    data = await RestoreStateData.async_get_instance(hass)
    await hass.async_block_till_done()
    await data.store.async_save([])

    # Emulate a fresh load
    hass.data.pop(DATA_RESTORE_STATE_TASK)

    entity = RestoreEntity()
    entity.hass = hass
    entity.entity_id = "input_boolean.b1"

    with patch(
        "homeassistant.helpers.restore_state.Store.async_save"
    ) as mock_write_data:
        await entity.async_get_last_state()
        await hass.async_block_till_done()

    # Startup Save
    assert mock_write_data.called

    with patch(
        "homeassistant.helpers.restore_state.Store.async_save"
    ) as mock_write_data:
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=10))
        await hass.async_block_till_done()

    # Not quite the first interval
    assert not mock_write_data.called

    with patch(
        "homeassistant.helpers.restore_state.Store.async_save"
    ) as mock_write_data:
        await RestoreStateData.async_save_persistent_states(hass)
        await hass.async_block_till_done()

    assert mock_write_data.called

    with patch(
        "homeassistant.helpers.restore_state.Store.async_save"
    ) as mock_write_data:
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=20))
        await hass.async_block_till_done()
    # Verify still saving
    assert mock_write_data.called

    with patch(
        "homeassistant.helpers.restore_state.Store.async_save"
    ) as mock_write_data:
        hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
        await hass.async_block_till_done()
    # Verify normal shutdown
    assert mock_write_data.called


async def test_hass_starting(hass: HomeAssistant) -> None:
    """Test that we cache data."""
    hass.state = CoreState.starting

    now = dt_util.utcnow()
    stored_states = [
        StoredState(State("input_boolean.b0", "on"), None, now),
        StoredState(State("input_boolean.b1", "on"), None, now),
        StoredState(State("input_boolean.b2", "on"), None, now),
    ]

    data = await RestoreStateData.async_get_instance(hass)
    await hass.async_block_till_done()
    await data.store.async_save([state.as_dict() for state in stored_states])

    # Emulate a fresh load
    hass.state = CoreState.not_running
    hass.data.pop(DATA_RESTORE_STATE_TASK)

    entity = RestoreEntity()
    entity.hass = hass
    entity.entity_id = "input_boolean.b1"

    # Mock that only b1 is present this run
    states = [State("input_boolean.b1", "on")]
    with patch(
        "homeassistant.helpers.restore_state.Store.async_save"
    ) as mock_write_data, patch.object(hass.states, "async_all", return_value=states):
        state = await entity.async_get_last_state()
        await hass.async_block_till_done()

    assert state is not None
    assert state.entity_id == "input_boolean.b1"
    assert state.state == "on"

    # Assert that no data was written yet, since hass is still starting.
    assert not mock_write_data.called

    # Finish hass startup
    with patch(
        "homeassistant.helpers.restore_state.Store.async_save"
    ) as mock_write_data:
        hass.bus.async_fire(EVENT_HOMEASSISTANT_START)
        await hass.async_block_till_done()

    # Assert that this session states were written
    assert mock_write_data.called


async def test_dump_data(hass: HomeAssistant) -> None:
    """Test that we cache data."""
    states = [
        State("input_boolean.b0", "on"),
        State("input_boolean.b1", "on"),
        State("input_boolean.b2", "on"),
        State("input_boolean.b5", "unavailable", {"restored": True}),
    ]

    entity = Entity()
    entity.hass = hass
    entity.entity_id = "input_boolean.b0"
    await entity.async_internal_added_to_hass()

    entity = RestoreEntity()
    entity.hass = hass
    entity.entity_id = "input_boolean.b1"
    await entity.async_internal_added_to_hass()

    data = await RestoreStateData.async_get_instance(hass)
    now = dt_util.utcnow()
    data.last_states = {
        "input_boolean.b0": StoredState(State("input_boolean.b0", "off"), None, now),
        "input_boolean.b1": StoredState(State("input_boolean.b1", "off"), None, now),
        "input_boolean.b2": StoredState(State("input_boolean.b2", "off"), None, now),
        "input_boolean.b3": StoredState(State("input_boolean.b3", "off"), None, now),
        "input_boolean.b4": StoredState(
            State("input_boolean.b4", "off"),
            None,
            datetime(1985, 10, 26, 1, 22, tzinfo=dt_util.UTC),
        ),
        "input_boolean.b5": StoredState(State("input_boolean.b5", "off"), None, now),
    }

    with patch(
        "homeassistant.helpers.restore_state.Store.async_save"
    ) as mock_write_data, patch.object(hass.states, "async_all", return_value=states):
        await data.async_dump_states()

    assert mock_write_data.called
    args = mock_write_data.mock_calls[0][1]
    written_states = args[0]

    # b0 should not be written, since it didn't extend RestoreEntity
    # b1 should be written, since it is present in the current run
    # b2 should not be written, since it is not registered with the helper
    # b3 should be written, since it is still not expired
    # b4 should not be written, since it is now expired
    # b5 should be written, since current state is restored by entity registry
    assert len(written_states) == 3
    assert written_states[0]["state"]["entity_id"] == "input_boolean.b1"
    assert written_states[0]["state"]["state"] == "on"
    assert written_states[1]["state"]["entity_id"] == "input_boolean.b3"
    assert written_states[1]["state"]["state"] == "off"
    assert written_states[2]["state"]["entity_id"] == "input_boolean.b5"
    assert written_states[2]["state"]["state"] == "off"

    # Test that removed entities are not persisted
    await entity.async_remove()

    with patch(
        "homeassistant.helpers.restore_state.Store.async_save"
    ) as mock_write_data, patch.object(hass.states, "async_all", return_value=states):
        await data.async_dump_states()

    assert mock_write_data.called
    args = mock_write_data.mock_calls[0][1]
    written_states = args[0]
    assert len(written_states) == 2
    assert written_states[0]["state"]["entity_id"] == "input_boolean.b3"
    assert written_states[0]["state"]["state"] == "off"
    assert written_states[1]["state"]["entity_id"] == "input_boolean.b5"
    assert written_states[1]["state"]["state"] == "off"


async def test_dump_error(hass: HomeAssistant) -> None:
    """Test that we cache data."""
    states = [
        State("input_boolean.b0", "on"),
        State("input_boolean.b1", "on"),
        State("input_boolean.b2", "on"),
    ]

    entity = Entity()
    entity.hass = hass
    entity.entity_id = "input_boolean.b0"
    await entity.async_internal_added_to_hass()

    entity = RestoreEntity()
    entity.hass = hass
    entity.entity_id = "input_boolean.b1"
    await entity.async_internal_added_to_hass()

    data = await RestoreStateData.async_get_instance(hass)

    with patch(
        "homeassistant.helpers.restore_state.Store.async_save",
        side_effect=HomeAssistantError,
    ) as mock_write_data, patch.object(hass.states, "async_all", return_value=states):
        await data.async_dump_states()

    assert mock_write_data.called


async def test_load_error(hass: HomeAssistant) -> None:
    """Test that we cache data."""
    entity = RestoreEntity()
    entity.hass = hass
    entity.entity_id = "input_boolean.b1"

    with patch(
        "homeassistant.helpers.storage.Store.async_load",
        side_effect=HomeAssistantError,
    ):
        state = await entity.async_get_last_state()

    assert state is None


async def test_state_saved_on_remove(hass: HomeAssistant) -> None:
    """Test that we save entity state on removal."""
    entity = RestoreEntity()
    entity.hass = hass
    entity.entity_id = "input_boolean.b0"
    await entity.async_internal_added_to_hass()

    now = dt_util.utcnow()
    hass.states.async_set(
        "input_boolean.b0", "on", {"complicated": {"value": {1, 2, now}}}
    )

    data = await RestoreStateData.async_get_instance(hass)

    # No last states should currently be saved
    assert not data.last_states

    await entity.async_remove()

    # We should store the input boolean state when it is removed
    state = data.last_states["input_boolean.b0"].state
    assert state.state == "on"
    assert isinstance(state.attributes["complicated"]["value"], list)
    assert set(state.attributes["complicated"]["value"]) == {1, 2, now.isoformat()}


async def test_restoring_invalid_entity_id(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Test restoring invalid entity IDs."""
    entity = RestoreEntity()
    entity.hass = hass
    entity.entity_id = "test.invalid__entity_id"
    now = dt_util.utcnow().isoformat()
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "key": STORAGE_KEY,
        "data": [
            {
                "state": {
                    "entity_id": "test.invalid__entity_id",
                    "state": "off",
                    "attributes": {},
                    "last_changed": now,
                    "last_updated": now,
                    "context": {
                        "id": "3c2243ff5f30447eb12e7348cfd5b8ff",
                        "user_id": None,
                    },
                },
                "last_seen": dt_util.utcnow().isoformat(),
            }
        ],
    }

    state = await entity.async_get_last_state()
    assert state is None
