"""The tests for the utility_meter sensor platform."""
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

import pytest

from homeassistant.components.select.const import (
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.components.sensor import (
    ATTR_STATE_CLASS,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.components.utility_meter.const import (
    ATTR_VALUE,
    DAILY,
    DOMAIN,
    HOURLY,
    QUARTER_HOURLY,
    SERVICE_CALIBRATE_METER,
)
from homeassistant.components.utility_meter.sensor import (
    ATTR_LAST_RESET,
    ATTR_STATUS,
    COLLECTING,
    PAUSED,
)
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    ENERGY_KILO_WATT_HOUR,
    EVENT_HOMEASSISTANT_START,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CoreState, State
from homeassistant.setup import async_setup_component
import homeassistant.util.dt as dt_util

from tests.common import MockConfigEntry, async_fire_time_changed, mock_restore_cache


@contextmanager
def alter_time(retval):
    """Manage multiple time mocks."""
    patch1 = patch("homeassistant.util.dt.utcnow", return_value=retval)
    patch2 = patch("homeassistant.util.dt.now", return_value=retval)

    with patch1, patch2:
        yield


@pytest.mark.parametrize(
    "yaml_config,config_entry_config",
    (
        (
            {
                "utility_meter": {
                    "energy_bill": {
                        "source": "sensor.energy",
                        "tariffs": ["onpeak", "midpeak", "offpeak"],
                    }
                }
            },
            None,
        ),
        (
            None,
            {
                "cycle": "none",
                "delta_values": False,
                "name": "Energy bill",
                "net_consumption": False,
                "offset": 0,
                "source": "sensor.energy",
                "tariffs": ["onpeak", "midpeak", "offpeak"],
            },
        ),
    ),
)
async def test_state(hass, yaml_config, config_entry_config):
    """Test utility sensor state."""
    if yaml_config:
        assert await async_setup_component(hass, DOMAIN, yaml_config)
        await hass.async_block_till_done()
        entity_id = yaml_config[DOMAIN]["energy_bill"]["source"]
    else:
        config_entry = MockConfigEntry(
            data={},
            domain=DOMAIN,
            options=config_entry_config,
            title=config_entry_config["name"],
        )
        config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        entity_id = config_entry_config["source"]

    hass.bus.async_fire(EVENT_HOMEASSISTANT_START)
    await hass.async_block_till_done()

    hass.states.async_set(
        entity_id, 2, {ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR}
    )
    await hass.async_block_till_done()

    state = hass.states.get("sensor.energy_bill_onpeak")
    assert state is not None
    assert state.state == "0"
    assert state.attributes.get("status") == COLLECTING
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == ENERGY_KILO_WATT_HOUR

    state = hass.states.get("sensor.energy_bill_midpeak")
    assert state is not None
    assert state.state == "0"
    assert state.attributes.get("status") == PAUSED
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == ENERGY_KILO_WATT_HOUR

    state = hass.states.get("sensor.energy_bill_offpeak")
    assert state is not None
    assert state.state == "0"
    assert state.attributes.get("status") == PAUSED
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == ENERGY_KILO_WATT_HOUR

    now = dt_util.utcnow() + timedelta(seconds=10)
    with patch("homeassistant.util.dt.utcnow", return_value=now):
        hass.states.async_set(
            entity_id,
            3,
            {ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR},
            force_update=True,
        )
        await hass.async_block_till_done()

    state = hass.states.get("sensor.energy_bill_onpeak")
    assert state is not None
    assert state.state == "1"
    assert state.attributes.get("status") == COLLECTING

    state = hass.states.get("sensor.energy_bill_midpeak")
    assert state is not None
    assert state.state == "0"
    assert state.attributes.get("status") == PAUSED

    state = hass.states.get("sensor.energy_bill_offpeak")
    assert state is not None
    assert state.state == "0"
    assert state.attributes.get("status") == PAUSED

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: "select.energy_bill", "option": "offpeak"},
        blocking=True,
    )

    await hass.async_block_till_done()

    now = dt_util.utcnow() + timedelta(seconds=20)
    with patch("homeassistant.util.dt.utcnow", return_value=now):
        hass.states.async_set(
            entity_id,
            6,
            {ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR},
            force_update=True,
        )
        await hass.async_block_till_done()

    state = hass.states.get("sensor.energy_bill_onpeak")
    assert state is not None
    assert state.state == "1"
    assert state.attributes.get("status") == PAUSED

    state = hass.states.get("sensor.energy_bill_midpeak")
    assert state is not None
    assert state.state == "0"
    assert state.attributes.get("status") == PAUSED

    state = hass.states.get("sensor.energy_bill_offpeak")
    assert state is not None
    assert state.state == "3"
    assert state.attributes.get("status") == COLLECTING

    await hass.services.async_call(
        DOMAIN,
        SERVICE_CALIBRATE_METER,
        {ATTR_ENTITY_ID: "sensor.energy_bill_midpeak", ATTR_VALUE: "100"},
        blocking=True,
    )
    await hass.async_block_till_done()
    state = hass.states.get("sensor.energy_bill_midpeak")
    assert state is not None
    assert state.state == "100"

    await hass.services.async_call(
        DOMAIN,
        SERVICE_CALIBRATE_METER,
        {ATTR_ENTITY_ID: "sensor.energy_bill_midpeak", ATTR_VALUE: "0.123"},
        blocking=True,
    )
    await hass.async_block_till_done()
    state = hass.states.get("sensor.energy_bill_midpeak")
    assert state is not None
    assert state.state == "0.123"

    # test invalid state
    hass.states.async_set(
        entity_id, "*", {ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR}
    )
    await hass.async_block_till_done()
    state = hass.states.get("sensor.energy_bill_midpeak")
    assert state is not None
    assert state.state == "0.123"

    # test unavailable source
    hass.states.async_set(
        entity_id, STATE_UNAVAILABLE, {ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR}
    )
    await hass.async_block_till_done()
    state = hass.states.get("sensor.energy_bill_midpeak")
    assert state is not None
    assert state.state == "0.123"


@pytest.mark.parametrize(
    "yaml_config",
    (
        (
            {
                "utility_meter": {
                    "energy_bill": {
                        "source": "sensor.energy",
                        "tariffs": ["onpeak", "onpeak"],
                    }
                }
            },
            None,
        ),
    ),
)
async def test_not_unique_tariffs(hass, yaml_config):
    """Test utility sensor state initializtion."""
    assert not await async_setup_component(hass, DOMAIN, yaml_config)


@pytest.mark.parametrize(
    "yaml_config,config_entry_config",
    (
        (
            {
                "utility_meter": {
                    "energy_bill": {
                        "source": "sensor.energy",
                        "tariffs": ["onpeak", "midpeak", "offpeak"],
                    }
                }
            },
            None,
        ),
        (
            None,
            {
                "cycle": "none",
                "delta_values": False,
                "name": "Energy bill",
                "net_consumption": False,
                "offset": 0,
                "source": "sensor.energy",
                "tariffs": ["onpeak", "midpeak", "offpeak"],
            },
        ),
    ),
)
async def test_init(hass, yaml_config, config_entry_config):
    """Test utility sensor state initializtion."""
    if yaml_config:
        assert await async_setup_component(hass, DOMAIN, yaml_config)
        await hass.async_block_till_done()
        entity_id = yaml_config[DOMAIN]["energy_bill"]["source"]
    else:
        config_entry = MockConfigEntry(
            data={},
            domain=DOMAIN,
            options=config_entry_config,
            title=config_entry_config["name"],
        )
        config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        entity_id = config_entry_config["source"]

    hass.bus.async_fire(EVENT_HOMEASSISTANT_START)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.energy_bill_onpeak")
    assert state is not None
    assert state.state == STATE_UNKNOWN

    state = hass.states.get("sensor.energy_bill_offpeak")
    assert state is not None
    assert state.state == STATE_UNKNOWN

    hass.states.async_set(
        entity_id, 2, {ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR}
    )

    await hass.async_block_till_done()

    state = hass.states.get("sensor.energy_bill_onpeak")
    assert state is not None
    assert state.state == "0"
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == ENERGY_KILO_WATT_HOUR

    state = hass.states.get("sensor.energy_bill_offpeak")
    assert state is not None
    assert state.state == "0"
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == ENERGY_KILO_WATT_HOUR


@pytest.mark.parametrize(
    "yaml_config,config_entry_configs",
    (
        (
            {
                "utility_meter": {
                    "energy_meter": {
                        "source": "sensor.energy",
                        "net_consumption": True,
                    },
                    "gas_meter": {
                        "source": "sensor.gas",
                    },
                }
            },
            None,
        ),
        (
            None,
            [
                {
                    "cycle": "none",
                    "delta_values": False,
                    "name": "Energy meter",
                    "net_consumption": True,
                    "offset": 0,
                    "source": "sensor.energy",
                    "tariffs": [],
                },
                {
                    "cycle": "none",
                    "delta_values": False,
                    "name": "Gas meter",
                    "net_consumption": False,
                    "offset": 0,
                    "source": "sensor.gas",
                    "tariffs": [],
                },
            ],
        ),
    ),
)
async def test_device_class(hass, yaml_config, config_entry_configs):
    """Test utility device_class."""
    if yaml_config:
        assert await async_setup_component(hass, DOMAIN, yaml_config)
        await hass.async_block_till_done()
    else:
        for config_entry_config in config_entry_configs:
            config_entry = MockConfigEntry(
                data={},
                domain=DOMAIN,
                options=config_entry_config,
                title=config_entry_config["name"],
            )
            config_entry.add_to_hass(hass)
            assert await hass.config_entries.async_setup(config_entry.entry_id)
            await hass.async_block_till_done()

    entity_id_energy = "sensor.energy"
    entity_id_gas = "sensor.gas"

    hass.bus.async_fire(EVENT_HOMEASSISTANT_START)
    await hass.async_block_till_done()

    hass.states.async_set(
        entity_id_energy, 2, {ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR}
    )
    hass.states.async_set(
        entity_id_gas, 2, {ATTR_UNIT_OF_MEASUREMENT: "some_archaic_unit"}
    )
    await hass.async_block_till_done()

    state = hass.states.get("sensor.energy_meter")
    assert state is not None
    assert state.state == "0"
    assert state.attributes.get(ATTR_DEVICE_CLASS) is SensorDeviceClass.ENERGY.value
    assert state.attributes.get(ATTR_STATE_CLASS) is SensorStateClass.TOTAL
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == ENERGY_KILO_WATT_HOUR

    state = hass.states.get("sensor.gas_meter")
    assert state is not None
    assert state.state == "0"
    assert state.attributes.get(ATTR_DEVICE_CLASS) is None
    assert state.attributes.get(ATTR_STATE_CLASS) is SensorStateClass.TOTAL_INCREASING
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == "some_archaic_unit"


@pytest.mark.parametrize(
    "yaml_config,config_entry_config",
    (
        (
            {
                "utility_meter": {
                    "energy_bill": {
                        "source": "sensor.energy",
                        "tariffs": ["onpeak", "midpeak", "offpeak"],
                    }
                }
            },
            None,
        ),
        (
            None,
            {
                "cycle": "none",
                "delta_values": False,
                "name": "Energy bill",
                "net_consumption": False,
                "offset": 0,
                "source": "sensor.energy",
                "tariffs": ["onpeak", "midpeak", "offpeak"],
            },
        ),
    ),
)
async def test_restore_state(hass, yaml_config, config_entry_config):
    """Test utility sensor restore state."""
    # Home assistant is not runnit yet
    hass.state = CoreState.not_running

    last_reset = "2020-12-21T00:00:00.013073+00:00"
    mock_restore_cache(
        hass,
        [
            State(
                "sensor.energy_bill_onpeak",
                "3",
                attributes={
                    ATTR_STATUS: PAUSED,
                    ATTR_LAST_RESET: last_reset,
                    ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
                },
            ),
            State(
                "sensor.energy_bill_midpeak",
                "error",
            ),
            State(
                "sensor.energy_bill_offpeak",
                "6",
                attributes={
                    ATTR_STATUS: COLLECTING,
                    ATTR_LAST_RESET: last_reset,
                    ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR,
                },
            ),
        ],
    )

    if yaml_config:
        assert await async_setup_component(hass, DOMAIN, yaml_config)
        await hass.async_block_till_done()
    else:
        config_entry = MockConfigEntry(
            data={},
            domain=DOMAIN,
            options=config_entry_config,
            title=config_entry_config["name"],
        )
        config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    # restore from cache
    state = hass.states.get("sensor.energy_bill_onpeak")
    assert state.state == "3"
    assert state.attributes.get("status") == PAUSED
    assert state.attributes.get("last_reset") == last_reset
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == ENERGY_KILO_WATT_HOUR

    state = hass.states.get("sensor.energy_bill_midpeak")
    assert state.state == STATE_UNKNOWN

    state = hass.states.get("sensor.energy_bill_offpeak")
    assert state.state == "6"
    assert state.attributes.get("status") == COLLECTING
    assert state.attributes.get("last_reset") == last_reset
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == ENERGY_KILO_WATT_HOUR

    # utility_meter is loaded, now set sensors according to utility_meter:
    hass.bus.async_fire(EVENT_HOMEASSISTANT_START)
    await hass.async_block_till_done()

    state = hass.states.get("select.energy_bill")
    assert state.state == "onpeak"

    state = hass.states.get("sensor.energy_bill_onpeak")
    assert state.attributes.get("status") == COLLECTING

    state = hass.states.get("sensor.energy_bill_offpeak")
    assert state.attributes.get("status") == PAUSED


@pytest.mark.parametrize(
    "yaml_config,config_entry_config",
    (
        (
            {
                "utility_meter": {
                    "energy_bill": {
                        "net_consumption": True,
                        "source": "sensor.energy",
                    }
                }
            },
            None,
        ),
        (
            None,
            {
                "cycle": "none",
                "delta_values": False,
                "name": "Energy bill",
                "net_consumption": True,
                "offset": 0,
                "source": "sensor.energy",
                "tariffs": [],
            },
        ),
    ),
)
async def test_net_consumption(hass, yaml_config, config_entry_config):
    """Test utility sensor state."""
    if yaml_config:
        assert await async_setup_component(hass, DOMAIN, yaml_config)
        await hass.async_block_till_done()
        entity_id = yaml_config[DOMAIN]["energy_bill"]["source"]
    else:
        config_entry = MockConfigEntry(
            data={},
            domain=DOMAIN,
            options=config_entry_config,
            title=config_entry_config["name"],
        )
        config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        entity_id = config_entry_config["source"]

    hass.bus.async_fire(EVENT_HOMEASSISTANT_START)
    hass.states.async_set(
        entity_id, 2, {ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR}
    )
    await hass.async_block_till_done()

    now = dt_util.utcnow() + timedelta(seconds=10)
    with patch("homeassistant.util.dt.utcnow", return_value=now):
        hass.states.async_set(
            entity_id,
            1,
            {ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR},
            force_update=True,
        )
        await hass.async_block_till_done()

    state = hass.states.get("sensor.energy_bill")
    assert state is not None

    assert state.state == "-1"


@pytest.mark.parametrize(
    "yaml_config,config_entry_config",
    (
        (
            {
                "utility_meter": {
                    "energy_bill": {
                        "net_consumption": False,
                        "source": "sensor.energy",
                    }
                }
            },
            None,
        ),
        (
            None,
            {
                "cycle": "none",
                "delta_values": False,
                "name": "Energy bill",
                "net_consumption": False,
                "offset": 0,
                "source": "sensor.energy",
                "tariffs": [],
            },
        ),
    ),
)
async def test_non_net_consumption(hass, yaml_config, config_entry_config, caplog):
    """Test utility sensor state."""
    if yaml_config:
        assert await async_setup_component(hass, DOMAIN, yaml_config)
        await hass.async_block_till_done()
        entity_id = yaml_config[DOMAIN]["energy_bill"]["source"]
    else:
        config_entry = MockConfigEntry(
            data={},
            domain=DOMAIN,
            options=config_entry_config,
            title=config_entry_config["name"],
        )
        config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        entity_id = config_entry_config["source"]

    hass.bus.async_fire(EVENT_HOMEASSISTANT_START)
    hass.states.async_set(
        entity_id, 2, {ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR}
    )
    await hass.async_block_till_done()

    now = dt_util.utcnow() + timedelta(seconds=10)
    with patch("homeassistant.util.dt.utcnow", return_value=now):
        hass.states.async_set(
            entity_id,
            1,
            {ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR},
            force_update=True,
        )
        await hass.async_block_till_done()

    now = dt_util.utcnow() + timedelta(seconds=10)
    with patch("homeassistant.util.dt.utcnow", return_value=now):
        hass.states.async_set(
            entity_id,
            None,
            {ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR},
            force_update=True,
        )
        await hass.async_block_till_done()
    assert "Invalid state " in caplog.text

    state = hass.states.get("sensor.energy_bill")
    assert state is not None

    assert state.state == "0"


@pytest.mark.parametrize(
    "yaml_config,config_entry_config",
    (
        (
            {
                "utility_meter": {
                    "energy_bill": {
                        "delta_values": True,
                        "source": "sensor.energy",
                    }
                }
            },
            None,
        ),
        (
            None,
            {
                "cycle": "none",
                "delta_values": True,
                "name": "Energy bill",
                "net_consumption": False,
                "offset": 0,
                "source": "sensor.energy",
                "tariffs": [],
            },
        ),
    ),
)
async def test_delta_values(hass, yaml_config, config_entry_config, caplog):
    """Test utility meter "delta_values" mode."""
    # Home assistant is not runnit yet
    hass.state = CoreState.not_running

    now = dt_util.utcnow()
    with alter_time(now):
        if yaml_config:
            assert await async_setup_component(hass, DOMAIN, yaml_config)
            await hass.async_block_till_done()
            entity_id = yaml_config[DOMAIN]["energy_bill"]["source"]
        else:
            config_entry = MockConfigEntry(
                data={},
                domain=DOMAIN,
                options=config_entry_config,
                title=config_entry_config["name"],
            )
            config_entry.add_to_hass(hass)
            assert await hass.config_entries.async_setup(config_entry.entry_id)
            await hass.async_block_till_done()
            entity_id = config_entry_config["source"]

        hass.bus.async_fire(EVENT_HOMEASSISTANT_START)

        async_fire_time_changed(hass, now)
        hass.states.async_set(
            entity_id, 1, {ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR}
        )
        await hass.async_block_till_done()

    state = hass.states.get("sensor.energy_bill")
    assert state.attributes.get("status") == PAUSED

    now += timedelta(seconds=30)
    with alter_time(now):
        async_fire_time_changed(hass, now)
        hass.states.async_set(
            entity_id,
            None,
            {ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR},
            force_update=True,
        )
        await hass.async_block_till_done()
    assert "Invalid adjustment of None" in caplog.text

    now += timedelta(seconds=30)
    with alter_time(now):
        async_fire_time_changed(hass, now)
        hass.states.async_set(
            entity_id,
            3,
            {ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR},
            force_update=True,
        )
        await hass.async_block_till_done()

    state = hass.states.get("sensor.energy_bill")
    assert state.attributes.get("status") == COLLECTING

    now += timedelta(seconds=30)
    with alter_time(now):
        async_fire_time_changed(hass, now)
        await hass.async_block_till_done()
        hass.states.async_set(
            entity_id,
            6,
            {ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR},
            force_update=True,
        )
        await hass.async_block_till_done()

    state = hass.states.get("sensor.energy_bill")
    assert state is not None

    assert state.state == "9"


def gen_config(cycle, offset=None):
    """Generate configuration."""
    config = {
        "utility_meter": {"energy_bill": {"source": "sensor.energy", "cycle": cycle}}
    }

    if offset:
        config["utility_meter"]["energy_bill"]["offset"] = {
            "days": offset.days,
            "seconds": offset.seconds,
        }
    return config


async def _test_self_reset(hass, config, start_time, expect_reset=True):
    """Test energy sensor self reset."""
    now = dt_util.parse_datetime(start_time)
    with alter_time(now):
        assert await async_setup_component(hass, DOMAIN, config)
        await hass.async_block_till_done()

        hass.bus.async_fire(EVENT_HOMEASSISTANT_START)
        entity_id = config[DOMAIN]["energy_bill"]["source"]

        async_fire_time_changed(hass, now)
        hass.states.async_set(
            entity_id, 1, {ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR}
        )
        await hass.async_block_till_done()

    now += timedelta(seconds=30)
    with alter_time(now):
        async_fire_time_changed(hass, now)
        hass.states.async_set(
            entity_id,
            3,
            {ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR},
            force_update=True,
        )
        await hass.async_block_till_done()

    now += timedelta(seconds=30)
    with alter_time(now):
        async_fire_time_changed(hass, now)
        await hass.async_block_till_done()
        hass.states.async_set(
            entity_id,
            6,
            {ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR},
            force_update=True,
        )
        await hass.async_block_till_done()

    state = hass.states.get("sensor.energy_bill")
    if expect_reset:
        assert state.attributes.get("last_period") == "2"
        assert state.attributes.get("last_reset") == now.isoformat()
        assert state.state == "3"
    else:
        assert state.attributes.get("last_period") == "0"
        assert state.state == "5"
        start_time_str = dt_util.parse_datetime(start_time).isoformat()
        assert state.attributes.get("last_reset") == start_time_str

    # Check next day when nothing should happen for weekly, monthly, bimonthly and yearly
    if config["utility_meter"]["energy_bill"].get("cycle") in [
        QUARTER_HOURLY,
        HOURLY,
        DAILY,
    ]:
        now += timedelta(minutes=5)
    else:
        now += timedelta(days=5)
    with alter_time(now):
        async_fire_time_changed(hass, now)
        await hass.async_block_till_done()
        hass.states.async_set(
            entity_id,
            10,
            {ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR},
            force_update=True,
        )
        await hass.async_block_till_done()
    state = hass.states.get("sensor.energy_bill")
    if expect_reset:
        assert state.attributes.get("last_period") == "2"
        assert state.state == "7"
    else:
        assert state.attributes.get("last_period") == "0"
        assert state.state == "9"


async def test_self_reset_cron_pattern(hass, legacy_patchable_time):
    """Test cron pattern reset of meter."""
    config = {
        "utility_meter": {
            "energy_bill": {"source": "sensor.energy", "cron": "0 0 1 * *"}
        }
    }

    await _test_self_reset(hass, config, "2017-01-31T23:59:00.000000+00:00")


async def test_self_reset_quarter_hourly(hass, legacy_patchable_time):
    """Test quarter-hourly reset of meter."""
    await _test_self_reset(
        hass, gen_config("quarter-hourly"), "2017-12-31T23:59:00.000000+00:00"
    )


async def test_self_reset_quarter_hourly_first_quarter(hass, legacy_patchable_time):
    """Test quarter-hourly reset of meter."""
    await _test_self_reset(
        hass, gen_config("quarter-hourly"), "2017-12-31T23:14:00.000000+00:00"
    )


async def test_self_reset_quarter_hourly_second_quarter(hass, legacy_patchable_time):
    """Test quarter-hourly reset of meter."""
    await _test_self_reset(
        hass, gen_config("quarter-hourly"), "2017-12-31T23:29:00.000000+00:00"
    )


async def test_self_reset_quarter_hourly_third_quarter(hass, legacy_patchable_time):
    """Test quarter-hourly reset of meter."""
    await _test_self_reset(
        hass, gen_config("quarter-hourly"), "2017-12-31T23:44:00.000000+00:00"
    )


async def test_self_reset_hourly(hass, legacy_patchable_time):
    """Test hourly reset of meter."""
    await _test_self_reset(
        hass, gen_config("hourly"), "2017-12-31T23:59:00.000000+00:00"
    )


async def test_self_reset_daily(hass, legacy_patchable_time):
    """Test daily reset of meter."""
    await _test_self_reset(
        hass, gen_config("daily"), "2017-12-31T23:59:00.000000+00:00"
    )


async def test_self_reset_weekly(hass, legacy_patchable_time):
    """Test weekly reset of meter."""
    await _test_self_reset(
        hass, gen_config("weekly"), "2017-12-31T23:59:00.000000+00:00"
    )


async def test_self_reset_monthly(hass, legacy_patchable_time):
    """Test monthly reset of meter."""
    await _test_self_reset(
        hass, gen_config("monthly"), "2017-12-31T23:59:00.000000+00:00"
    )


async def test_self_reset_bimonthly(hass, legacy_patchable_time):
    """Test bimonthly reset of meter occurs on even months."""
    await _test_self_reset(
        hass, gen_config("bimonthly"), "2017-12-31T23:59:00.000000+00:00"
    )


async def test_self_no_reset_bimonthly(hass, legacy_patchable_time):
    """Test bimonthly reset of meter does not occur on odd months."""
    await _test_self_reset(
        hass,
        gen_config("bimonthly"),
        "2018-01-01T23:59:00.000000+00:00",
        expect_reset=False,
    )


async def test_self_reset_quarterly(hass, legacy_patchable_time):
    """Test quarterly reset of meter."""
    await _test_self_reset(
        hass, gen_config("quarterly"), "2017-03-31T23:59:00.000000+00:00"
    )


async def test_self_reset_yearly(hass, legacy_patchable_time):
    """Test yearly reset of meter."""
    await _test_self_reset(
        hass, gen_config("yearly"), "2017-12-31T23:59:00.000000+00:00"
    )


async def test_self_no_reset_yearly(hass, legacy_patchable_time):
    """Test yearly reset of meter does not occur after 1st January."""
    await _test_self_reset(
        hass,
        gen_config("yearly"),
        "2018-01-01T23:59:00.000000+00:00",
        expect_reset=False,
    )


async def test_reset_yearly_offset(hass, legacy_patchable_time):
    """Test yearly reset of meter."""
    await _test_self_reset(
        hass,
        gen_config("yearly", timedelta(days=1, minutes=10)),
        "2018-01-02T00:09:00.000000+00:00",
    )


async def test_no_reset_yearly_offset(hass, legacy_patchable_time):
    """Test yearly reset of meter."""
    await _test_self_reset(
        hass,
        gen_config("yearly", timedelta(27)),
        "2018-04-29T23:59:00.000000+00:00",
        expect_reset=False,
    )


async def test_bad_offset(hass, legacy_patchable_time):
    """Test bad offset of meter."""
    assert not await async_setup_component(
        hass, DOMAIN, gen_config("monthly", timedelta(days=31))
    )
