"""The tests the History component."""
from __future__ import annotations

# pylint: disable=protected-access,invalid-name
from copy import copy
from datetime import datetime, timedelta
import importlib
import json
import sys
from unittest.mock import patch, sentinel

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from homeassistant.components import recorder
from homeassistant.components.recorder import core, history, statistics
from homeassistant.components.recorder.models import process_timestamp
from homeassistant.components.recorder.util import session_scope
from homeassistant.core import State
from homeassistant.helpers.json import JSONEncoder
import homeassistant.util.dt as dt_util

from .common import wait_recording_done

CREATE_ENGINE_TARGET = "homeassistant.components.recorder.core.create_engine"
SCHEMA_MODULE = "tests.components.recorder.db_schema_30"


def _create_engine_test(*args, **kwargs):
    """Test version of create_engine that initializes with old schema.

    This simulates an existing db with the old schema.
    """
    importlib.import_module(SCHEMA_MODULE)
    old_db_schema = sys.modules[SCHEMA_MODULE]
    engine = create_engine(*args, **kwargs)
    old_db_schema.Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            recorder.db_schema.StatisticsRuns(start=statistics.get_start_time())
        )
        session.add(
            recorder.db_schema.SchemaChanges(
                schema_version=old_db_schema.SCHEMA_VERSION
            )
        )
        session.commit()
    return engine


@pytest.fixture(autouse=True)
def db_schema_30():
    """Fixture to initialize the db with the old schema."""
    importlib.import_module(SCHEMA_MODULE)
    old_db_schema = sys.modules[SCHEMA_MODULE]

    with patch.object(recorder, "db_schema", old_db_schema), patch.object(
        recorder.migration, "SCHEMA_VERSION", old_db_schema.SCHEMA_VERSION
    ), patch.object(core, "EventData", old_db_schema.EventData), patch.object(
        core, "States", old_db_schema.States
    ), patch.object(
        core, "Events", old_db_schema.Events
    ), patch.object(
        core, "StateAttributes", old_db_schema.StateAttributes
    ), patch(
        CREATE_ENGINE_TARGET, new=_create_engine_test
    ):
        yield


def test_get_full_significant_states_with_session_entity_no_matches(hass_recorder):
    """Test getting states at a specific point in time for entities that never have been recorded."""
    hass = hass_recorder()
    now = dt_util.utcnow()
    time_before_recorder_ran = now - timedelta(days=1000)
    with session_scope(hass=hass) as session:
        assert (
            history.get_full_significant_states_with_session(
                hass, session, time_before_recorder_ran, now, entity_ids=["demo.id"]
            )
            == {}
        )
        assert (
            history.get_full_significant_states_with_session(
                hass,
                session,
                time_before_recorder_ran,
                now,
                entity_ids=["demo.id", "demo.id2"],
            )
            == {}
        )


def test_significant_states_with_session_entity_minimal_response_no_matches(
    hass_recorder,
):
    """Test getting states at a specific point in time for entities that never have been recorded."""
    hass = hass_recorder()
    now = dt_util.utcnow()
    time_before_recorder_ran = now - timedelta(days=1000)
    with session_scope(hass=hass) as session:
        assert (
            history.get_significant_states_with_session(
                hass,
                session,
                time_before_recorder_ran,
                now,
                entity_ids=["demo.id"],
                minimal_response=True,
            )
            == {}
        )
        assert (
            history.get_significant_states_with_session(
                hass,
                session,
                time_before_recorder_ran,
                now,
                entity_ids=["demo.id", "demo.id2"],
                minimal_response=True,
            )
            == {}
        )


@pytest.mark.parametrize(
    "attributes, no_attributes, limit",
    [
        ({"attr": True}, False, 5000),
        ({}, True, 5000),
        ({"attr": True}, False, 3),
        ({}, True, 3),
    ],
)
def test_state_changes_during_period(hass_recorder, attributes, no_attributes, limit):
    """Test state change during period."""
    hass = hass_recorder()
    entity_id = "media_player.test"

    def set_state(state):
        """Set the state."""
        hass.states.set(entity_id, state, attributes)
        wait_recording_done(hass)
        return hass.states.get(entity_id)

    start = dt_util.utcnow()
    point = start + timedelta(seconds=1)
    end = point + timedelta(seconds=1)

    with patch(
        "homeassistant.components.recorder.core.dt_util.utcnow", return_value=start
    ):
        set_state("idle")
        set_state("YouTube")

    with patch(
        "homeassistant.components.recorder.core.dt_util.utcnow", return_value=point
    ):
        states = [
            set_state("idle"),
            set_state("Netflix"),
            set_state("Plex"),
            set_state("YouTube"),
        ]

    with patch(
        "homeassistant.components.recorder.core.dt_util.utcnow", return_value=end
    ):
        set_state("Netflix")
        set_state("Plex")

    hist = history.state_changes_during_period(
        hass, start, end, entity_id, no_attributes, limit=limit
    )

    assert states[:limit] == hist[entity_id]


def test_state_changes_during_period_descending(hass_recorder):
    """Test state change during period descending."""
    hass = hass_recorder()
    entity_id = "media_player.test"

    def set_state(state):
        """Set the state."""
        hass.states.set(entity_id, state, {"any": 1})
        wait_recording_done(hass)
        return hass.states.get(entity_id)

    start = dt_util.utcnow()
    point = start + timedelta(seconds=1)
    point2 = start + timedelta(seconds=1, microseconds=2)
    point3 = start + timedelta(seconds=1, microseconds=3)
    point4 = start + timedelta(seconds=1, microseconds=4)
    end = point + timedelta(seconds=1)

    with patch(
        "homeassistant.components.recorder.core.dt_util.utcnow", return_value=start
    ):
        set_state("idle")
        set_state("YouTube")

    with patch(
        "homeassistant.components.recorder.core.dt_util.utcnow", return_value=point
    ):
        states = [set_state("idle")]
    with patch(
        "homeassistant.components.recorder.core.dt_util.utcnow", return_value=point2
    ):
        states.append(set_state("Netflix"))
    with patch(
        "homeassistant.components.recorder.core.dt_util.utcnow", return_value=point3
    ):
        states.append(set_state("Plex"))
    with patch(
        "homeassistant.components.recorder.core.dt_util.utcnow", return_value=point4
    ):
        states.append(set_state("YouTube"))

    with patch(
        "homeassistant.components.recorder.core.dt_util.utcnow", return_value=end
    ):
        set_state("Netflix")
        set_state("Plex")

    hist = history.state_changes_during_period(
        hass, start, end, entity_id, no_attributes=False, descending=False
    )
    assert states == hist[entity_id]

    hist = history.state_changes_during_period(
        hass, start, end, entity_id, no_attributes=False, descending=True
    )
    assert states == list(reversed(list(hist[entity_id])))


def test_get_last_state_changes(hass_recorder):
    """Test number of state changes."""
    hass = hass_recorder()
    entity_id = "sensor.test"

    def set_state(state):
        """Set the state."""
        hass.states.set(entity_id, state)
        wait_recording_done(hass)
        return hass.states.get(entity_id)

    start = dt_util.utcnow() - timedelta(minutes=2)
    point = start + timedelta(minutes=1)
    point2 = point + timedelta(minutes=1)

    with patch(
        "homeassistant.components.recorder.core.dt_util.utcnow", return_value=start
    ):
        set_state("1")

    states = []
    with patch(
        "homeassistant.components.recorder.core.dt_util.utcnow", return_value=point
    ):
        states.append(set_state("2"))

    with patch(
        "homeassistant.components.recorder.core.dt_util.utcnow", return_value=point2
    ):
        states.append(set_state("3"))

    hist = history.get_last_state_changes(hass, 2, entity_id)

    assert states == hist[entity_id]


def test_ensure_state_can_be_copied(hass_recorder):
    """Ensure a state can pass though copy().

    The filter integration uses copy() on states
    from history.
    """
    hass = hass_recorder()
    entity_id = "sensor.test"

    def set_state(state):
        """Set the state."""
        hass.states.set(entity_id, state)
        wait_recording_done(hass)
        return hass.states.get(entity_id)

    start = dt_util.utcnow() - timedelta(minutes=2)
    point = start + timedelta(minutes=1)

    with patch(
        "homeassistant.components.recorder.core.dt_util.utcnow", return_value=start
    ):
        set_state("1")

    with patch(
        "homeassistant.components.recorder.core.dt_util.utcnow", return_value=point
    ):
        set_state("2")

    hist = history.get_last_state_changes(hass, 2, entity_id)

    assert copy(hist[entity_id][0]) == hist[entity_id][0]
    assert copy(hist[entity_id][1]) == hist[entity_id][1]


def test_get_significant_states(hass_recorder):
    """Test that only significant states are returned.

    We should get back every thermostat change that
    includes an attribute change, but only the state updates for
    media player (attribute changes are not significant and not returned).
    """
    hass = hass_recorder()
    zero, four, states = record_states(hass)
    hist = history.get_significant_states(hass, zero, four)
    assert states == hist


def test_get_significant_states_minimal_response(hass_recorder):
    """Test that only significant states are returned.

    When minimal responses is set only the first and
    last states return a complete state.
    We should get back every thermostat change that
    includes an attribute change, but only the state updates for
    media player (attribute changes are not significant and not returned).
    """
    hass = hass_recorder()
    zero, four, states = record_states(hass)
    hist = history.get_significant_states(hass, zero, four, minimal_response=True)
    entites_with_reducable_states = [
        "media_player.test",
        "media_player.test3",
    ]

    # All states for media_player.test state are reduced
    # down to last_changed and state when minimal_response
    # is set except for the first state.
    # is set.  We use JSONEncoder to make sure that are
    # pre-encoded last_changed is always the same as what
    # will happen with encoding a native state
    for entity_id in entites_with_reducable_states:
        entity_states = states[entity_id]
        for state_idx in range(1, len(entity_states)):
            input_state = entity_states[state_idx]
            orig_last_changed = orig_last_changed = json.dumps(
                process_timestamp(input_state.last_changed),
                cls=JSONEncoder,
            ).replace('"', "")
            orig_state = input_state.state
            entity_states[state_idx] = {
                "last_changed": orig_last_changed,
                "state": orig_state,
            }
    assert states == hist


def test_get_significant_states_with_initial(hass_recorder):
    """Test that only significant states are returned.

    We should get back every thermostat change that
    includes an attribute change, but only the state updates for
    media player (attribute changes are not significant and not returned).
    """
    hass = hass_recorder()
    zero, four, states = record_states(hass)
    one = zero + timedelta(seconds=1)
    one_and_half = zero + timedelta(seconds=1.5)
    for entity_id in states:
        if entity_id == "media_player.test":
            states[entity_id] = states[entity_id][1:]
        for state in states[entity_id]:
            if state.last_changed == one:
                state.last_changed = one_and_half

    hist = history.get_significant_states(
        hass,
        one_and_half,
        four,
        include_start_time_state=True,
    )
    assert states == hist


def test_get_significant_states_without_initial(hass_recorder):
    """Test that only significant states are returned.

    We should get back every thermostat change that
    includes an attribute change, but only the state updates for
    media player (attribute changes are not significant and not returned).
    """
    hass = hass_recorder()
    zero, four, states = record_states(hass)
    one = zero + timedelta(seconds=1)
    one_and_half = zero + timedelta(seconds=1.5)
    for entity_id in states:
        states[entity_id] = list(
            filter(lambda s: s.last_changed != one, states[entity_id])
        )
    del states["media_player.test2"]

    hist = history.get_significant_states(
        hass,
        one_and_half,
        four,
        include_start_time_state=False,
    )
    assert states == hist


def test_get_significant_states_entity_id(hass_recorder):
    """Test that only significant states are returned for one entity."""
    hass = hass_recorder()
    zero, four, states = record_states(hass)
    del states["media_player.test2"]
    del states["media_player.test3"]
    del states["thermostat.test"]
    del states["thermostat.test2"]
    del states["script.can_cancel_this_one"]

    hist = history.get_significant_states(hass, zero, four, ["media_player.test"])
    assert states == hist


def test_get_significant_states_multiple_entity_ids(hass_recorder):
    """Test that only significant states are returned for one entity."""
    hass = hass_recorder()
    zero, four, states = record_states(hass)
    del states["media_player.test2"]
    del states["media_player.test3"]
    del states["thermostat.test2"]
    del states["script.can_cancel_this_one"]

    hist = history.get_significant_states(
        hass,
        zero,
        four,
        ["media_player.test", "thermostat.test"],
    )
    assert states == hist


def test_get_significant_states_are_ordered(hass_recorder):
    """Test order of results from get_significant_states.

    When entity ids are given, the results should be returned with the data
    in the same order.
    """
    hass = hass_recorder()
    zero, four, _states = record_states(hass)
    entity_ids = ["media_player.test", "media_player.test2"]
    hist = history.get_significant_states(hass, zero, four, entity_ids)
    assert list(hist.keys()) == entity_ids
    entity_ids = ["media_player.test2", "media_player.test"]
    hist = history.get_significant_states(hass, zero, four, entity_ids)
    assert list(hist.keys()) == entity_ids


def test_get_significant_states_only(hass_recorder):
    """Test significant states when significant_states_only is set."""
    hass = hass_recorder()
    entity_id = "sensor.test"

    def set_state(state, **kwargs):
        """Set the state."""
        hass.states.set(entity_id, state, **kwargs)
        wait_recording_done(hass)
        return hass.states.get(entity_id)

    start = dt_util.utcnow() - timedelta(minutes=4)
    points = []
    for i in range(1, 4):
        points.append(start + timedelta(minutes=i))

    states = []
    with patch(
        "homeassistant.components.recorder.core.dt_util.utcnow", return_value=start
    ):
        set_state("123", attributes={"attribute": 10.64})

    with patch(
        "homeassistant.components.recorder.core.dt_util.utcnow",
        return_value=points[0],
    ):
        # Attributes are different, state not
        states.append(set_state("123", attributes={"attribute": 21.42}))

    with patch(
        "homeassistant.components.recorder.core.dt_util.utcnow",
        return_value=points[1],
    ):
        # state is different, attributes not
        states.append(set_state("32", attributes={"attribute": 21.42}))

    with patch(
        "homeassistant.components.recorder.core.dt_util.utcnow",
        return_value=points[2],
    ):
        # everything is different
        states.append(set_state("412", attributes={"attribute": 54.23}))

    hist = history.get_significant_states(hass, start, significant_changes_only=True)

    assert len(hist[entity_id]) == 2
    assert states[0] not in hist[entity_id]
    assert states[1] in hist[entity_id]
    assert states[2] in hist[entity_id]

    hist = history.get_significant_states(hass, start, significant_changes_only=False)

    assert len(hist[entity_id]) == 3
    assert states == hist[entity_id]


def record_states(hass) -> tuple[datetime, datetime, dict[str, list[State]]]:
    """Record some test states.

    We inject a bunch of state updates from media player, zone and
    thermostat.
    """
    mp = "media_player.test"
    mp2 = "media_player.test2"
    mp3 = "media_player.test3"
    therm = "thermostat.test"
    therm2 = "thermostat.test2"
    zone = "zone.home"
    script_c = "script.can_cancel_this_one"

    def set_state(entity_id, state, **kwargs):
        """Set the state."""
        hass.states.set(entity_id, state, **kwargs)
        wait_recording_done(hass)
        return hass.states.get(entity_id)

    zero = dt_util.utcnow()
    one = zero + timedelta(seconds=1)
    two = one + timedelta(seconds=1)
    three = two + timedelta(seconds=1)
    four = three + timedelta(seconds=1)

    states = {therm: [], therm2: [], mp: [], mp2: [], mp3: [], script_c: []}
    with patch(
        "homeassistant.components.recorder.core.dt_util.utcnow", return_value=one
    ):
        states[mp].append(
            set_state(mp, "idle", attributes={"media_title": str(sentinel.mt1)})
        )
        states[mp].append(
            set_state(mp, "YouTube", attributes={"media_title": str(sentinel.mt2)})
        )
        states[mp2].append(
            set_state(mp2, "YouTube", attributes={"media_title": str(sentinel.mt2)})
        )
        states[mp3].append(
            set_state(mp3, "idle", attributes={"media_title": str(sentinel.mt1)})
        )
        states[therm].append(
            set_state(therm, 20, attributes={"current_temperature": 19.5})
        )

    with patch(
        "homeassistant.components.recorder.core.dt_util.utcnow", return_value=two
    ):
        # This state will be skipped only different in time
        set_state(mp, "YouTube", attributes={"media_title": str(sentinel.mt3)})
        # This state will be skipped because domain is excluded
        set_state(zone, "zoning")
        states[script_c].append(
            set_state(script_c, "off", attributes={"can_cancel": True})
        )
        states[therm].append(
            set_state(therm, 21, attributes={"current_temperature": 19.8})
        )
        states[therm2].append(
            set_state(therm2, 20, attributes={"current_temperature": 19})
        )

    with patch(
        "homeassistant.components.recorder.core.dt_util.utcnow", return_value=three
    ):
        states[mp].append(
            set_state(mp, "Netflix", attributes={"media_title": str(sentinel.mt4)})
        )
        states[mp3].append(
            set_state(mp3, "Netflix", attributes={"media_title": str(sentinel.mt3)})
        )
        # Attributes changed even though state is the same
        states[therm].append(
            set_state(therm, 21, attributes={"current_temperature": 20})
        )

    return zero, four, states


def test_state_changes_during_period_multiple_entities_single_test(hass_recorder):
    """Test state change during period with multiple entities in the same test.

    This test ensures the sqlalchemy query cache does not
    generate incorrect results.
    """
    hass = hass_recorder()
    start = dt_util.utcnow()
    test_entites = {f"sensor.{i}": str(i) for i in range(30)}
    for entity_id, value in test_entites.items():
        hass.states.set(entity_id, value)

    wait_recording_done(hass)
    end = dt_util.utcnow()

    hist = history.state_changes_during_period(hass, start, end, None)
    for entity_id, value in test_entites.items():
        hist[entity_id][0].state == value

    for entity_id, value in test_entites.items():
        hist = history.state_changes_during_period(hass, start, end, entity_id)
        assert len(hist) == 1
        hist[entity_id][0].state == value

    hist = history.state_changes_during_period(hass, start, end, None)
    for entity_id, value in test_entites.items():
        hist[entity_id][0].state == value
