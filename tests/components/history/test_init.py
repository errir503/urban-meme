"""The tests the History component."""
# pylint: disable=protected-access,invalid-name
from datetime import timedelta
from http import HTTPStatus
import json
from unittest.mock import patch, sentinel

import pytest
from pytest import approx

from homeassistant.components import history, recorder
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.components.recorder.models import process_timestamp
import homeassistant.core as ha
from homeassistant.helpers.json import JSONEncoder
from homeassistant.setup import async_setup_component
import homeassistant.util.dt as dt_util
from homeassistant.util.unit_system import IMPERIAL_SYSTEM, METRIC_SYSTEM

from tests.common import async_init_recorder_component, init_recorder_component
from tests.components.recorder.common import (
    async_wait_recording_done_without_instance,
    trigger_db_commit,
    wait_recording_done,
)


@pytest.mark.usefixtures("hass_history")
def test_setup():
    """Test setup method of history."""
    # Verification occurs in the fixture
    pass


def test_get_significant_states(hass_history):
    """Test that only significant states are returned.

    We should get back every thermostat change that
    includes an attribute change, but only the state updates for
    media player (attribute changes are not significant and not returned).
    """
    hass = hass_history
    zero, four, states = record_states(hass)
    hist = get_significant_states(hass, zero, four, filters=history.Filters())
    assert states == hist


def test_get_significant_states_minimal_response(hass_history):
    """Test that only significant states are returned.

    When minimal responses is set only the first and
    last states return a complete state.

    We should get back every thermostat change that
    includes an attribute change, but only the state updates for
    media player (attribute changes are not significant and not returned).
    """
    hass = hass_history
    zero, four, states = record_states(hass)
    hist = get_significant_states(
        hass, zero, four, filters=history.Filters(), minimal_response=True
    )

    # The second media_player.test state is reduced
    # down to last_changed and state when minimal_response
    # is set.  We use JSONEncoder to make sure that are
    # pre-encoded last_changed is always the same as what
    # will happen with encoding a native state
    input_state = states["media_player.test"][1]
    orig_last_changed = json.dumps(
        process_timestamp(input_state.last_changed),
        cls=JSONEncoder,
    ).replace('"', "")
    orig_state = input_state.state
    states["media_player.test"][1] = {
        "last_changed": orig_last_changed,
        "state": orig_state,
    }

    assert states == hist


def test_get_significant_states_with_initial(hass_history):
    """Test that only significant states are returned.

    We should get back every thermostat change that
    includes an attribute change, but only the state updates for
    media player (attribute changes are not significant and not returned).
    """
    hass = hass_history
    zero, four, states = record_states(hass)
    one = zero + timedelta(seconds=1)
    one_and_half = zero + timedelta(seconds=1.5)
    for entity_id in states:
        if entity_id == "media_player.test":
            states[entity_id] = states[entity_id][1:]
        for state in states[entity_id]:
            if state.last_changed == one:
                state.last_changed = one_and_half

    hist = get_significant_states(
        hass,
        one_and_half,
        four,
        filters=history.Filters(),
        include_start_time_state=True,
    )
    assert states == hist


def test_get_significant_states_without_initial(hass_history):
    """Test that only significant states are returned.

    We should get back every thermostat change that
    includes an attribute change, but only the state updates for
    media player (attribute changes are not significant and not returned).
    """
    hass = hass_history
    zero, four, states = record_states(hass)
    one = zero + timedelta(seconds=1)
    one_and_half = zero + timedelta(seconds=1.5)
    for entity_id in states:
        states[entity_id] = list(
            filter(lambda s: s.last_changed != one, states[entity_id])
        )
    del states["media_player.test2"]

    hist = get_significant_states(
        hass,
        one_and_half,
        four,
        filters=history.Filters(),
        include_start_time_state=False,
    )
    assert states == hist


def test_get_significant_states_entity_id(hass_history):
    """Test that only significant states are returned for one entity."""
    hass = hass_history
    zero, four, states = record_states(hass)
    del states["media_player.test2"]
    del states["media_player.test3"]
    del states["thermostat.test"]
    del states["thermostat.test2"]
    del states["script.can_cancel_this_one"]

    hist = get_significant_states(
        hass, zero, four, ["media_player.test"], filters=history.Filters()
    )
    assert states == hist


def test_get_significant_states_multiple_entity_ids(hass_history):
    """Test that only significant states are returned for one entity."""
    hass = hass_history
    zero, four, states = record_states(hass)
    del states["media_player.test2"]
    del states["media_player.test3"]
    del states["thermostat.test2"]
    del states["script.can_cancel_this_one"]

    hist = get_significant_states(
        hass,
        zero,
        four,
        ["media_player.test", "thermostat.test"],
        filters=history.Filters(),
    )
    assert states == hist


def test_get_significant_states_exclude_domain(hass_history):
    """Test if significant states are returned when excluding domains.

    We should get back every thermostat change that includes an attribute
    change, but no media player changes.
    """
    hass = hass_history
    zero, four, states = record_states(hass)
    del states["media_player.test"]
    del states["media_player.test2"]
    del states["media_player.test3"]

    config = history.CONFIG_SCHEMA(
        {
            ha.DOMAIN: {},
            history.DOMAIN: {
                history.CONF_EXCLUDE: {history.CONF_DOMAINS: ["media_player"]}
            },
        }
    )
    check_significant_states(hass, zero, four, states, config)


def test_get_significant_states_exclude_entity(hass_history):
    """Test if significant states are returned when excluding entities.

    We should get back every thermostat and script changes, but no media
    player changes.
    """
    hass = hass_history
    zero, four, states = record_states(hass)
    del states["media_player.test"]

    config = history.CONFIG_SCHEMA(
        {
            ha.DOMAIN: {},
            history.DOMAIN: {
                history.CONF_EXCLUDE: {history.CONF_ENTITIES: ["media_player.test"]}
            },
        }
    )
    check_significant_states(hass, zero, four, states, config)


def test_get_significant_states_exclude(hass_history):
    """Test significant states when excluding entities and domains.

    We should not get back every thermostat and media player test changes.
    """
    hass = hass_history
    zero, four, states = record_states(hass)
    del states["media_player.test"]
    del states["thermostat.test"]
    del states["thermostat.test2"]

    config = history.CONFIG_SCHEMA(
        {
            ha.DOMAIN: {},
            history.DOMAIN: {
                history.CONF_EXCLUDE: {
                    history.CONF_DOMAINS: ["thermostat"],
                    history.CONF_ENTITIES: ["media_player.test"],
                }
            },
        }
    )
    check_significant_states(hass, zero, four, states, config)


def test_get_significant_states_exclude_include_entity(hass_history):
    """Test significant states when excluding domains and include entities.

    We should not get back every thermostat and media player test changes.
    """
    hass = hass_history
    zero, four, states = record_states(hass)
    del states["media_player.test2"]
    del states["media_player.test3"]
    del states["thermostat.test"]
    del states["thermostat.test2"]
    del states["script.can_cancel_this_one"]

    config = history.CONFIG_SCHEMA(
        {
            ha.DOMAIN: {},
            history.DOMAIN: {
                history.CONF_INCLUDE: {
                    history.CONF_ENTITIES: ["media_player.test", "thermostat.test"]
                },
                history.CONF_EXCLUDE: {history.CONF_DOMAINS: ["thermostat"]},
            },
        }
    )
    check_significant_states(hass, zero, four, states, config)


def test_get_significant_states_include_domain(hass_history):
    """Test if significant states are returned when including domains.

    We should get back every thermostat and script changes, but no media
    player changes.
    """
    hass = hass_history
    zero, four, states = record_states(hass)
    del states["media_player.test"]
    del states["media_player.test2"]
    del states["media_player.test3"]

    config = history.CONFIG_SCHEMA(
        {
            ha.DOMAIN: {},
            history.DOMAIN: {
                history.CONF_INCLUDE: {history.CONF_DOMAINS: ["thermostat", "script"]}
            },
        }
    )
    check_significant_states(hass, zero, four, states, config)


def test_get_significant_states_include_entity(hass_history):
    """Test if significant states are returned when including entities.

    We should only get back changes of the media_player.test entity.
    """
    hass = hass_history
    zero, four, states = record_states(hass)
    del states["media_player.test2"]
    del states["media_player.test3"]
    del states["thermostat.test"]
    del states["thermostat.test2"]
    del states["script.can_cancel_this_one"]

    config = history.CONFIG_SCHEMA(
        {
            ha.DOMAIN: {},
            history.DOMAIN: {
                history.CONF_INCLUDE: {history.CONF_ENTITIES: ["media_player.test"]}
            },
        }
    )
    check_significant_states(hass, zero, four, states, config)


def test_get_significant_states_include(hass_history):
    """Test significant states when including domains and entities.

    We should only get back changes of the media_player.test entity and the
    thermostat domain.
    """
    hass = hass_history
    zero, four, states = record_states(hass)
    del states["media_player.test2"]
    del states["media_player.test3"]
    del states["script.can_cancel_this_one"]

    config = history.CONFIG_SCHEMA(
        {
            ha.DOMAIN: {},
            history.DOMAIN: {
                history.CONF_INCLUDE: {
                    history.CONF_DOMAINS: ["thermostat"],
                    history.CONF_ENTITIES: ["media_player.test"],
                }
            },
        }
    )
    check_significant_states(hass, zero, four, states, config)


def test_get_significant_states_include_exclude_domain(hass_history):
    """Test if significant states when excluding and including domains.

    We should not get back any changes since we include only the
    media_player domain but also exclude it.
    """
    hass = hass_history
    zero, four, states = record_states(hass)
    del states["media_player.test"]
    del states["media_player.test2"]
    del states["media_player.test3"]
    del states["thermostat.test"]
    del states["thermostat.test2"]
    del states["script.can_cancel_this_one"]

    config = history.CONFIG_SCHEMA(
        {
            ha.DOMAIN: {},
            history.DOMAIN: {
                history.CONF_INCLUDE: {history.CONF_DOMAINS: ["media_player"]},
                history.CONF_EXCLUDE: {history.CONF_DOMAINS: ["media_player"]},
            },
        }
    )
    check_significant_states(hass, zero, four, states, config)


def test_get_significant_states_include_exclude_entity(hass_history):
    """Test if significant states when excluding and including domains.

    We should not get back any changes since we include only
    media_player.test but also exclude it.
    """
    hass = hass_history
    zero, four, states = record_states(hass)
    del states["media_player.test"]
    del states["media_player.test2"]
    del states["media_player.test3"]
    del states["thermostat.test"]
    del states["thermostat.test2"]
    del states["script.can_cancel_this_one"]

    config = history.CONFIG_SCHEMA(
        {
            ha.DOMAIN: {},
            history.DOMAIN: {
                history.CONF_INCLUDE: {history.CONF_ENTITIES: ["media_player.test"]},
                history.CONF_EXCLUDE: {history.CONF_ENTITIES: ["media_player.test"]},
            },
        }
    )
    check_significant_states(hass, zero, four, states, config)


def test_get_significant_states_include_exclude(hass_history):
    """Test if significant states when in/excluding domains and entities.

    We should only get back changes of the media_player.test2 entity.
    """
    hass = hass_history
    zero, four, states = record_states(hass)
    del states["media_player.test"]
    del states["thermostat.test"]
    del states["thermostat.test2"]
    del states["script.can_cancel_this_one"]

    config = history.CONFIG_SCHEMA(
        {
            ha.DOMAIN: {},
            history.DOMAIN: {
                history.CONF_INCLUDE: {
                    history.CONF_DOMAINS: ["media_player"],
                    history.CONF_ENTITIES: ["thermostat.test"],
                },
                history.CONF_EXCLUDE: {
                    history.CONF_DOMAINS: ["thermostat"],
                    history.CONF_ENTITIES: ["media_player.test"],
                },
            },
        }
    )
    check_significant_states(hass, zero, four, states, config)


def test_get_significant_states_are_ordered(hass_history):
    """Test order of results from get_significant_states.

    When entity ids are given, the results should be returned with the data
    in the same order.
    """
    hass = hass_history
    zero, four, _states = record_states(hass)
    entity_ids = ["media_player.test", "media_player.test2"]
    hist = get_significant_states(
        hass, zero, four, entity_ids, filters=history.Filters()
    )
    assert list(hist.keys()) == entity_ids
    entity_ids = ["media_player.test2", "media_player.test"]
    hist = get_significant_states(
        hass, zero, four, entity_ids, filters=history.Filters()
    )
    assert list(hist.keys()) == entity_ids


def test_get_significant_states_only(hass_history):
    """Test significant states when significant_states_only is set."""
    hass = hass_history
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
    with patch("homeassistant.components.recorder.dt_util.utcnow", return_value=start):
        set_state("123", attributes={"attribute": 10.64})

    with patch(
        "homeassistant.components.recorder.dt_util.utcnow", return_value=points[0]
    ):
        # Attributes are different, state not
        states.append(set_state("123", attributes={"attribute": 21.42}))

    with patch(
        "homeassistant.components.recorder.dt_util.utcnow", return_value=points[1]
    ):
        # state is different, attributes not
        states.append(set_state("32", attributes={"attribute": 21.42}))

    with patch(
        "homeassistant.components.recorder.dt_util.utcnow", return_value=points[2]
    ):
        # everything is different
        states.append(set_state("412", attributes={"attribute": 54.23}))

    hist = get_significant_states(hass, start, significant_changes_only=True)

    assert len(hist[entity_id]) == 2
    assert states[0] not in hist[entity_id]
    assert states[1] in hist[entity_id]
    assert states[2] in hist[entity_id]

    hist = get_significant_states(hass, start, significant_changes_only=False)

    assert len(hist[entity_id]) == 3
    assert states == hist[entity_id]


def check_significant_states(hass, zero, four, states, config):
    """Check if significant states are retrieved."""
    filters = history.Filters()
    exclude = config[history.DOMAIN].get(history.CONF_EXCLUDE)
    if exclude:
        filters.excluded_entities = exclude.get(history.CONF_ENTITIES, [])
        filters.excluded_domains = exclude.get(history.CONF_DOMAINS, [])
    include = config[history.DOMAIN].get(history.CONF_INCLUDE)
    if include:
        filters.included_entities = include.get(history.CONF_ENTITIES, [])
        filters.included_domains = include.get(history.CONF_DOMAINS, [])

    hist = get_significant_states(hass, zero, four, filters=filters)
    assert states == hist


def record_states(hass):
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
    with patch("homeassistant.components.recorder.dt_util.utcnow", return_value=one):
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

    with patch("homeassistant.components.recorder.dt_util.utcnow", return_value=two):
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

    with patch("homeassistant.components.recorder.dt_util.utcnow", return_value=three):
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


async def test_fetch_period_api(hass, hass_client):
    """Test the fetch period view for history."""
    await hass.async_add_executor_job(init_recorder_component, hass)
    await async_setup_component(hass, "history", {})
    await hass.async_add_executor_job(hass.data[recorder.DATA_INSTANCE].block_till_done)
    client = await hass_client()
    response = await client.get(f"/api/history/period/{dt_util.utcnow().isoformat()}")
    assert response.status == HTTPStatus.OK


async def test_fetch_period_api_with_use_include_order(hass, hass_client):
    """Test the fetch period view for history with include order."""
    await hass.async_add_executor_job(init_recorder_component, hass)
    await async_setup_component(
        hass, "history", {history.DOMAIN: {history.CONF_ORDER: True}}
    )
    await hass.async_add_executor_job(hass.data[recorder.DATA_INSTANCE].block_till_done)
    client = await hass_client()
    response = await client.get(f"/api/history/period/{dt_util.utcnow().isoformat()}")
    assert response.status == HTTPStatus.OK


async def test_fetch_period_api_with_minimal_response(hass, hass_client):
    """Test the fetch period view for history with minimal_response."""
    await async_init_recorder_component(hass)
    now = dt_util.utcnow()
    await async_setup_component(hass, "history", {})

    hass.states.async_set("sensor.power", 0, {"attr": "any"})
    await async_wait_recording_done_without_instance(hass)
    hass.states.async_set("sensor.power", 50, {"attr": "any"})
    await async_wait_recording_done_without_instance(hass)
    hass.states.async_set("sensor.power", 23, {"attr": "any"})
    await async_wait_recording_done_without_instance(hass)
    client = await hass_client()
    response = await client.get(
        f"/api/history/period/{now.isoformat()}?filter_entity_id=sensor.power&minimal_response&no_attributes"
    )
    assert response.status == HTTPStatus.OK
    response_json = await response.json()
    assert len(response_json[0]) == 3
    state_list = response_json[0]

    assert state_list[0]["entity_id"] == "sensor.power"
    assert state_list[0]["attributes"] == {}
    assert state_list[0]["state"] == "0"

    assert "attributes" not in state_list[1]
    assert "entity_id" not in state_list[1]
    assert state_list[1]["state"] == "50"

    assert state_list[2]["entity_id"] == "sensor.power"
    assert state_list[2]["attributes"] == {}
    assert state_list[2]["state"] == "23"


async def test_fetch_period_api_with_no_timestamp(hass, hass_client):
    """Test the fetch period view for history with no timestamp."""
    await hass.async_add_executor_job(init_recorder_component, hass)
    await async_setup_component(hass, "history", {})
    await hass.async_add_executor_job(hass.data[recorder.DATA_INSTANCE].block_till_done)
    client = await hass_client()
    response = await client.get("/api/history/period")
    assert response.status == HTTPStatus.OK


async def test_fetch_period_api_with_include_order(hass, hass_client):
    """Test the fetch period view for history."""
    await hass.async_add_executor_job(init_recorder_component, hass)
    await async_setup_component(
        hass,
        "history",
        {
            "history": {
                "use_include_order": True,
                "include": {"entities": ["light.kitchen"]},
            }
        },
    )
    await hass.async_add_executor_job(hass.data[recorder.DATA_INSTANCE].block_till_done)
    client = await hass_client()
    response = await client.get(
        f"/api/history/period/{dt_util.utcnow().isoformat()}",
        params={"filter_entity_id": "non.existing,something.else"},
    )
    assert response.status == HTTPStatus.OK


async def test_fetch_period_api_with_entity_glob_include(hass, hass_client):
    """Test the fetch period view for history."""
    await hass.async_add_executor_job(init_recorder_component, hass)
    await async_setup_component(
        hass,
        "history",
        {
            "history": {
                "include": {"entity_globs": ["light.k*"]},
            }
        },
    )
    await hass.async_add_executor_job(hass.data[recorder.DATA_INSTANCE].block_till_done)
    hass.states.async_set("light.kitchen", "on")
    hass.states.async_set("light.cow", "on")
    hass.states.async_set("light.nomatch", "on")

    await hass.async_block_till_done()

    await hass.async_add_executor_job(trigger_db_commit, hass)
    await hass.async_block_till_done()
    await hass.async_add_executor_job(hass.data[recorder.DATA_INSTANCE].block_till_done)

    client = await hass_client()
    response = await client.get(
        f"/api/history/period/{dt_util.utcnow().isoformat()}",
    )
    assert response.status == HTTPStatus.OK
    response_json = await response.json()
    assert response_json[0][0]["entity_id"] == "light.kitchen"


async def test_fetch_period_api_with_entity_glob_exclude(hass, hass_client):
    """Test the fetch period view for history."""
    await hass.async_add_executor_job(init_recorder_component, hass)
    await async_setup_component(
        hass,
        "history",
        {
            "history": {
                "exclude": {
                    "entity_globs": ["light.k*"],
                    "domains": "switch",
                    "entities": "media_player.test",
                },
            }
        },
    )
    await hass.async_add_executor_job(hass.data[recorder.DATA_INSTANCE].block_till_done)
    hass.states.async_set("light.kitchen", "on")
    hass.states.async_set("light.cow", "on")
    hass.states.async_set("light.match", "on")
    hass.states.async_set("switch.match", "on")
    hass.states.async_set("media_player.test", "on")

    await hass.async_block_till_done()

    await hass.async_add_executor_job(trigger_db_commit, hass)
    await hass.async_block_till_done()
    await hass.async_add_executor_job(hass.data[recorder.DATA_INSTANCE].block_till_done)

    client = await hass_client()
    response = await client.get(
        f"/api/history/period/{dt_util.utcnow().isoformat()}",
    )
    assert response.status == HTTPStatus.OK
    response_json = await response.json()
    assert len(response_json) == 2
    assert response_json[0][0]["entity_id"] == "light.cow"
    assert response_json[1][0]["entity_id"] == "light.match"


async def test_fetch_period_api_with_entity_glob_include_and_exclude(hass, hass_client):
    """Test the fetch period view for history."""
    await hass.async_add_executor_job(init_recorder_component, hass)
    await async_setup_component(
        hass,
        "history",
        {
            "history": {
                "exclude": {
                    "entity_globs": ["light.many*"],
                },
                "include": {
                    "entity_globs": ["light.m*"],
                    "domains": "switch",
                    "entities": "media_player.test",
                },
            }
        },
    )
    await hass.async_add_executor_job(hass.data[recorder.DATA_INSTANCE].block_till_done)
    hass.states.async_set("light.kitchen", "on")
    hass.states.async_set("light.cow", "on")
    hass.states.async_set("light.match", "on")
    hass.states.async_set("light.many_state_changes", "on")
    hass.states.async_set("switch.match", "on")
    hass.states.async_set("media_player.test", "on")

    await hass.async_block_till_done()

    await hass.async_add_executor_job(trigger_db_commit, hass)
    await hass.async_block_till_done()
    await hass.async_add_executor_job(hass.data[recorder.DATA_INSTANCE].block_till_done)

    client = await hass_client()
    response = await client.get(
        f"/api/history/period/{dt_util.utcnow().isoformat()}",
    )
    assert response.status == HTTPStatus.OK
    response_json = await response.json()
    assert len(response_json) == 3
    assert response_json[0][0]["entity_id"] == "light.match"
    assert response_json[1][0]["entity_id"] == "media_player.test"
    assert response_json[2][0]["entity_id"] == "switch.match"


async def test_entity_ids_limit_via_api(hass, hass_client):
    """Test limiting history to entity_ids."""
    await hass.async_add_executor_job(init_recorder_component, hass)
    await async_setup_component(
        hass,
        "history",
        {"history": {}},
    )
    await hass.async_add_executor_job(hass.data[recorder.DATA_INSTANCE].block_till_done)
    hass.states.async_set("light.kitchen", "on")
    hass.states.async_set("light.cow", "on")
    hass.states.async_set("light.nomatch", "on")

    await hass.async_block_till_done()

    await hass.async_add_executor_job(trigger_db_commit, hass)
    await hass.async_block_till_done()
    await hass.async_add_executor_job(hass.data[recorder.DATA_INSTANCE].block_till_done)

    client = await hass_client()
    response = await client.get(
        f"/api/history/period/{dt_util.utcnow().isoformat()}?filter_entity_id=light.kitchen,light.cow",
    )
    assert response.status == HTTPStatus.OK
    response_json = await response.json()
    assert len(response_json) == 2
    assert response_json[0][0]["entity_id"] == "light.kitchen"
    assert response_json[1][0]["entity_id"] == "light.cow"


async def test_entity_ids_limit_via_api_with_skip_initial_state(hass, hass_client):
    """Test limiting history to entity_ids with skip_initial_state."""
    await hass.async_add_executor_job(init_recorder_component, hass)
    await async_setup_component(
        hass,
        "history",
        {"history": {}},
    )
    await hass.async_add_executor_job(hass.data[recorder.DATA_INSTANCE].block_till_done)
    hass.states.async_set("light.kitchen", "on")
    hass.states.async_set("light.cow", "on")
    hass.states.async_set("light.nomatch", "on")

    await hass.async_block_till_done()

    await hass.async_add_executor_job(trigger_db_commit, hass)
    await hass.async_block_till_done()
    await hass.async_add_executor_job(hass.data[recorder.DATA_INSTANCE].block_till_done)

    client = await hass_client()
    response = await client.get(
        f"/api/history/period/{dt_util.utcnow().isoformat()}?filter_entity_id=light.kitchen,light.cow&skip_initial_state",
    )
    assert response.status == HTTPStatus.OK
    response_json = await response.json()
    assert len(response_json) == 0

    when = dt_util.utcnow() - timedelta(minutes=1)
    response = await client.get(
        f"/api/history/period/{when.isoformat()}?filter_entity_id=light.kitchen,light.cow&skip_initial_state",
    )
    assert response.status == HTTPStatus.OK
    response_json = await response.json()
    assert len(response_json) == 2
    assert response_json[0][0]["entity_id"] == "light.kitchen"
    assert response_json[1][0]["entity_id"] == "light.cow"


POWER_SENSOR_ATTRIBUTES = {
    "device_class": "power",
    "state_class": "measurement",
    "unit_of_measurement": "kW",
}
PRESSURE_SENSOR_ATTRIBUTES = {
    "device_class": "pressure",
    "state_class": "measurement",
    "unit_of_measurement": "hPa",
}
TEMPERATURE_SENSOR_ATTRIBUTES = {
    "device_class": "temperature",
    "state_class": "measurement",
    "unit_of_measurement": "°C",
}


@pytest.mark.parametrize(
    "units, attributes, state, value",
    [
        (IMPERIAL_SYSTEM, POWER_SENSOR_ATTRIBUTES, 10, 10000),
        (METRIC_SYSTEM, POWER_SENSOR_ATTRIBUTES, 10, 10000),
        (IMPERIAL_SYSTEM, TEMPERATURE_SENSOR_ATTRIBUTES, 10, 50),
        (METRIC_SYSTEM, TEMPERATURE_SENSOR_ATTRIBUTES, 10, 10),
        (IMPERIAL_SYSTEM, PRESSURE_SENSOR_ATTRIBUTES, 1000, 14.503774389728312),
        (METRIC_SYSTEM, PRESSURE_SENSOR_ATTRIBUTES, 1000, 100000),
    ],
)
async def test_statistics_during_period(
    hass, hass_ws_client, units, attributes, state, value
):
    """Test statistics_during_period."""
    now = dt_util.utcnow()

    hass.config.units = units
    await hass.async_add_executor_job(init_recorder_component, hass)
    await async_setup_component(hass, "history", {})
    await async_setup_component(hass, "sensor", {})
    await hass.async_add_executor_job(hass.data[recorder.DATA_INSTANCE].block_till_done)
    hass.states.async_set("sensor.test", state, attributes=attributes)
    await hass.async_block_till_done()

    await hass.async_add_executor_job(trigger_db_commit, hass)
    await hass.async_block_till_done()

    hass.data[recorder.DATA_INSTANCE].do_adhoc_statistics(start=now)
    await hass.async_add_executor_job(hass.data[recorder.DATA_INSTANCE].block_till_done)

    client = await hass_ws_client()
    await client.send_json(
        {
            "id": 1,
            "type": "history/statistics_during_period",
            "start_time": now.isoformat(),
            "end_time": now.isoformat(),
            "statistic_ids": ["sensor.test"],
            "period": "hour",
        }
    )
    response = await client.receive_json()
    assert response["success"]
    assert response["result"] == {}

    await client.send_json(
        {
            "id": 2,
            "type": "history/statistics_during_period",
            "start_time": now.isoformat(),
            "statistic_ids": ["sensor.test"],
            "period": "5minute",
        }
    )
    response = await client.receive_json()
    assert response["success"]
    assert response["result"] == {
        "sensor.test": [
            {
                "statistic_id": "sensor.test",
                "start": now.isoformat(),
                "end": (now + timedelta(minutes=5)).isoformat(),
                "mean": approx(value),
                "min": approx(value),
                "max": approx(value),
                "last_reset": None,
                "state": None,
                "sum": None,
            }
        ]
    }


async def test_statistics_during_period_bad_start_time(hass, hass_ws_client):
    """Test statistics_during_period."""
    await hass.async_add_executor_job(init_recorder_component, hass)
    await async_setup_component(
        hass,
        "history",
        {"history": {}},
    )
    await hass.async_add_executor_job(hass.data[recorder.DATA_INSTANCE].block_till_done)

    client = await hass_ws_client()
    await client.send_json(
        {
            "id": 1,
            "type": "history/statistics_during_period",
            "start_time": "cats",
            "period": "5minute",
        }
    )
    response = await client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "invalid_start_time"


async def test_statistics_during_period_bad_end_time(hass, hass_ws_client):
    """Test statistics_during_period."""
    now = dt_util.utcnow()

    await hass.async_add_executor_job(init_recorder_component, hass)
    await async_setup_component(
        hass,
        "history",
        {"history": {}},
    )
    await hass.async_add_executor_job(hass.data[recorder.DATA_INSTANCE].block_till_done)

    client = await hass_ws_client()
    await client.send_json(
        {
            "id": 1,
            "type": "history/statistics_during_period",
            "start_time": now.isoformat(),
            "end_time": "dogs",
            "period": "5minute",
        }
    )
    response = await client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "invalid_end_time"


@pytest.mark.parametrize(
    "units, attributes, unit",
    [
        (IMPERIAL_SYSTEM, POWER_SENSOR_ATTRIBUTES, "W"),
        (METRIC_SYSTEM, POWER_SENSOR_ATTRIBUTES, "W"),
        (IMPERIAL_SYSTEM, TEMPERATURE_SENSOR_ATTRIBUTES, "°F"),
        (METRIC_SYSTEM, TEMPERATURE_SENSOR_ATTRIBUTES, "°C"),
        (IMPERIAL_SYSTEM, PRESSURE_SENSOR_ATTRIBUTES, "psi"),
        (METRIC_SYSTEM, PRESSURE_SENSOR_ATTRIBUTES, "Pa"),
    ],
)
async def test_list_statistic_ids(hass, hass_ws_client, units, attributes, unit):
    """Test list_statistic_ids."""
    now = dt_util.utcnow()

    hass.config.units = units
    await hass.async_add_executor_job(init_recorder_component, hass)
    await async_setup_component(hass, "history", {"history": {}})
    await async_setup_component(hass, "sensor", {})
    await hass.async_add_executor_job(hass.data[recorder.DATA_INSTANCE].block_till_done)

    client = await hass_ws_client()
    await client.send_json({"id": 1, "type": "history/list_statistic_ids"})
    response = await client.receive_json()
    assert response["success"]
    assert response["result"] == []

    hass.states.async_set("sensor.test", 10, attributes=attributes)
    await hass.async_block_till_done()

    await hass.async_add_executor_job(trigger_db_commit, hass)
    await hass.async_block_till_done()

    await client.send_json({"id": 2, "type": "history/list_statistic_ids"})
    response = await client.receive_json()
    assert response["success"]
    assert response["result"] == [
        {
            "statistic_id": "sensor.test",
            "has_mean": True,
            "has_sum": False,
            "name": None,
            "source": "recorder",
            "unit_of_measurement": unit,
        }
    ]

    hass.data[recorder.DATA_INSTANCE].do_adhoc_statistics(start=now)
    await hass.async_add_executor_job(hass.data[recorder.DATA_INSTANCE].block_till_done)
    # Remove the state, statistics will now be fetched from the database
    hass.states.async_remove("sensor.test")
    await hass.async_block_till_done()

    await client.send_json({"id": 3, "type": "history/list_statistic_ids"})
    response = await client.receive_json()
    assert response["success"]
    assert response["result"] == [
        {
            "statistic_id": "sensor.test",
            "has_mean": True,
            "has_sum": False,
            "name": None,
            "source": "recorder",
            "unit_of_measurement": unit,
        }
    ]

    await client.send_json(
        {"id": 4, "type": "history/list_statistic_ids", "statistic_type": "dogs"}
    )
    response = await client.receive_json()
    assert not response["success"]

    await client.send_json(
        {"id": 5, "type": "history/list_statistic_ids", "statistic_type": "mean"}
    )
    response = await client.receive_json()
    assert response["success"]
    assert response["result"] == [
        {
            "statistic_id": "sensor.test",
            "has_mean": True,
            "has_sum": False,
            "name": None,
            "source": "recorder",
            "unit_of_measurement": unit,
        }
    ]

    await client.send_json(
        {"id": 6, "type": "history/list_statistic_ids", "statistic_type": "sum"}
    )
    response = await client.receive_json()
    assert response["success"]
    assert response["result"] == []
