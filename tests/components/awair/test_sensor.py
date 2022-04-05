"""Tests for the Awair sensor platform."""
from unittest.mock import patch

from homeassistant.components.awair.const import (
    API_CO2,
    API_HUMID,
    API_LUX,
    API_PM10,
    API_PM25,
    API_SCORE,
    API_SPL_A,
    API_TEMP,
    API_VOC,
    DOMAIN,
    SENSOR_TYPE_SCORE,
    SENSOR_TYPES,
    SENSOR_TYPES_DUST,
)
from homeassistant.const import (
    ATTR_ICON,
    ATTR_UNIT_OF_MEASUREMENT,
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONCENTRATION_PARTS_PER_BILLION,
    CONCENTRATION_PARTS_PER_MILLION,
    LIGHT_LUX,
    PERCENTAGE,
    STATE_UNAVAILABLE,
    TEMP_CELSIUS,
)
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_component import async_update_entity

from .const import (
    AWAIR_UUID,
    CONFIG,
    DEVICES_FIXTURE,
    GEN1_DATA_FIXTURE,
    GEN2_DATA_FIXTURE,
    GLOW_DATA_FIXTURE,
    MINT_DATA_FIXTURE,
    OFFLINE_FIXTURE,
    OMNI_DATA_FIXTURE,
    UNIQUE_ID,
    USER_FIXTURE,
)

from tests.common import MockConfigEntry

SENSOR_TYPES_MAP = {
    desc.key: desc for desc in (SENSOR_TYPE_SCORE, *SENSOR_TYPES, *SENSOR_TYPES_DUST)
}


async def setup_awair(hass, fixtures):
    """Add Awair devices to hass, using specified fixtures for data."""

    entry = MockConfigEntry(domain=DOMAIN, unique_id=UNIQUE_ID, data=CONFIG)
    with patch("python_awair.AwairClient.query", side_effect=fixtures):
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


def assert_expected_properties(
    hass, registry, name, unique_id, state_value, attributes
):
    """Assert expected properties from a dict."""

    entry = registry.async_get(name)
    assert entry.unique_id == unique_id
    state = hass.states.get(name)
    assert state
    assert state.state == state_value
    for attr, value in attributes.items():
        assert state.attributes.get(attr) == value


async def test_awair_gen1_sensors(hass):
    """Test expected sensors on a 1st gen Awair."""

    fixtures = [USER_FIXTURE, DEVICES_FIXTURE, GEN1_DATA_FIXTURE]
    await setup_awair(hass, fixtures)
    registry = er.async_get(hass)

    assert_expected_properties(
        hass,
        registry,
        "sensor.living_room_awair_score",
        f"{AWAIR_UUID}_{SENSOR_TYPES_MAP[API_SCORE].unique_id_tag}",
        "88",
        {ATTR_ICON: "mdi:blur"},
    )

    assert_expected_properties(
        hass,
        registry,
        "sensor.living_room_temperature",
        f"{AWAIR_UUID}_{SENSOR_TYPES_MAP[API_TEMP].unique_id_tag}",
        "21.8",
        {ATTR_UNIT_OF_MEASUREMENT: TEMP_CELSIUS, "awair_index": 1.0},
    )

    assert_expected_properties(
        hass,
        registry,
        "sensor.living_room_humidity",
        f"{AWAIR_UUID}_{SENSOR_TYPES_MAP[API_HUMID].unique_id_tag}",
        "41.59",
        {ATTR_UNIT_OF_MEASUREMENT: PERCENTAGE, "awair_index": 0.0},
    )

    assert_expected_properties(
        hass,
        registry,
        "sensor.living_room_carbon_dioxide",
        f"{AWAIR_UUID}_{SENSOR_TYPES_MAP[API_CO2].unique_id_tag}",
        "654.0",
        {
            ATTR_ICON: "mdi:cloud",
            ATTR_UNIT_OF_MEASUREMENT: CONCENTRATION_PARTS_PER_MILLION,
            "awair_index": 0.0,
        },
    )

    assert_expected_properties(
        hass,
        registry,
        "sensor.living_room_volatile_organic_compounds",
        f"{AWAIR_UUID}_{SENSOR_TYPES_MAP[API_VOC].unique_id_tag}",
        "366",
        {
            ATTR_ICON: "mdi:cloud",
            ATTR_UNIT_OF_MEASUREMENT: CONCENTRATION_PARTS_PER_BILLION,
            "awair_index": 1.0,
        },
    )

    assert_expected_properties(
        hass,
        registry,
        "sensor.living_room_pm2_5",
        # gen1 unique_id should be awair_12345-DUST, which matches old integration behavior
        f"{AWAIR_UUID}_DUST",
        "14.3",
        {
            ATTR_ICON: "mdi:blur",
            ATTR_UNIT_OF_MEASUREMENT: CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
            "awair_index": 1.0,
        },
    )

    assert_expected_properties(
        hass,
        registry,
        "sensor.living_room_pm10",
        f"{AWAIR_UUID}_{SENSOR_TYPES_MAP[API_PM10].unique_id_tag}",
        "14.3",
        {
            ATTR_ICON: "mdi:blur",
            ATTR_UNIT_OF_MEASUREMENT: CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
            "awair_index": 1.0,
        },
    )

    # We should not have a dust sensor; it's aliased as pm2.5
    # and pm10 sensors.
    assert hass.states.get("sensor.living_room_dust") is None

    # We should not have sound or lux sensors.
    assert hass.states.get("sensor.living_room_sound_level") is None
    assert hass.states.get("sensor.living_room_illuminance") is None


async def test_awair_gen2_sensors(hass):
    """Test expected sensors on a 2nd gen Awair."""

    fixtures = [USER_FIXTURE, DEVICES_FIXTURE, GEN2_DATA_FIXTURE]
    await setup_awair(hass, fixtures)
    registry = er.async_get(hass)

    assert_expected_properties(
        hass,
        registry,
        "sensor.living_room_awair_score",
        f"{AWAIR_UUID}_{SENSOR_TYPES_MAP[API_SCORE].unique_id_tag}",
        "97",
        {ATTR_ICON: "mdi:blur"},
    )

    assert_expected_properties(
        hass,
        registry,
        "sensor.living_room_pm2_5",
        f"{AWAIR_UUID}_{SENSOR_TYPES_MAP[API_PM25].unique_id_tag}",
        "2.0",
        {
            ATTR_ICON: "mdi:blur",
            ATTR_UNIT_OF_MEASUREMENT: CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
            "awair_index": 0.0,
        },
    )

    # The Awair 2nd gen reports specifically a pm2.5 sensor,
    # and so we don't alias anything. Make sure we didn't do that.
    assert hass.states.get("sensor.living_room_pm10") is None


async def test_awair_mint_sensors(hass):
    """Test expected sensors on an Awair mint."""

    fixtures = [USER_FIXTURE, DEVICES_FIXTURE, MINT_DATA_FIXTURE]
    await setup_awair(hass, fixtures)
    registry = er.async_get(hass)

    assert_expected_properties(
        hass,
        registry,
        "sensor.living_room_awair_score",
        f"{AWAIR_UUID}_{SENSOR_TYPES_MAP[API_SCORE].unique_id_tag}",
        "98",
        {ATTR_ICON: "mdi:blur"},
    )

    assert_expected_properties(
        hass,
        registry,
        "sensor.living_room_pm2_5",
        f"{AWAIR_UUID}_{SENSOR_TYPES_MAP[API_PM25].unique_id_tag}",
        "1.0",
        {
            ATTR_ICON: "mdi:blur",
            ATTR_UNIT_OF_MEASUREMENT: CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
            "awair_index": 0.0,
        },
    )

    assert_expected_properties(
        hass,
        registry,
        "sensor.living_room_illuminance",
        f"{AWAIR_UUID}_{SENSOR_TYPES_MAP[API_LUX].unique_id_tag}",
        "441.7",
        {ATTR_UNIT_OF_MEASUREMENT: LIGHT_LUX},
    )

    # The Mint does not have a CO2 sensor.
    assert hass.states.get("sensor.living_room_carbon_dioxide") is None


async def test_awair_glow_sensors(hass):
    """Test expected sensors on an Awair glow."""

    fixtures = [USER_FIXTURE, DEVICES_FIXTURE, GLOW_DATA_FIXTURE]
    await setup_awair(hass, fixtures)
    registry = er.async_get(hass)

    assert_expected_properties(
        hass,
        registry,
        "sensor.living_room_awair_score",
        f"{AWAIR_UUID}_{SENSOR_TYPES_MAP[API_SCORE].unique_id_tag}",
        "93",
        {ATTR_ICON: "mdi:blur"},
    )

    # The glow does not have a particle sensor
    assert hass.states.get("sensor.living_room_pm2_5") is None


async def test_awair_omni_sensors(hass):
    """Test expected sensors on an Awair omni."""

    fixtures = [USER_FIXTURE, DEVICES_FIXTURE, OMNI_DATA_FIXTURE]
    await setup_awair(hass, fixtures)
    registry = er.async_get(hass)

    assert_expected_properties(
        hass,
        registry,
        "sensor.living_room_awair_score",
        f"{AWAIR_UUID}_{SENSOR_TYPES_MAP[API_SCORE].unique_id_tag}",
        "99",
        {ATTR_ICON: "mdi:blur"},
    )

    assert_expected_properties(
        hass,
        registry,
        "sensor.living_room_sound_level",
        f"{AWAIR_UUID}_{SENSOR_TYPES_MAP[API_SPL_A].unique_id_tag}",
        "47.0",
        {ATTR_ICON: "mdi:ear-hearing", ATTR_UNIT_OF_MEASUREMENT: "dBa"},
    )

    assert_expected_properties(
        hass,
        registry,
        "sensor.living_room_illuminance",
        f"{AWAIR_UUID}_{SENSOR_TYPES_MAP[API_LUX].unique_id_tag}",
        "804.9",
        {ATTR_UNIT_OF_MEASUREMENT: LIGHT_LUX},
    )


async def test_awair_offline(hass):
    """Test expected behavior when an Awair is offline."""

    fixtures = [USER_FIXTURE, DEVICES_FIXTURE, OFFLINE_FIXTURE]
    await setup_awair(hass, fixtures)

    # The expected behavior is that we won't have any sensors
    # if the device is not online when we set it up. python_awair
    # does not make any assumptions about what sensors a device
    # might have - they are created dynamically.

    # We check for the absence of the "awair score", which every
    # device *should* have if it's online. If we don't see it,
    # then we probably didn't set anything up. Which is correct,
    # in this case.
    assert hass.states.get("sensor.living_room_awair_score") is None


async def test_awair_unavailable(hass):
    """Test expected behavior when an Awair becomes offline later."""

    fixtures = [USER_FIXTURE, DEVICES_FIXTURE, GEN1_DATA_FIXTURE]
    await setup_awair(hass, fixtures)
    registry = er.async_get(hass)

    assert_expected_properties(
        hass,
        registry,
        "sensor.living_room_awair_score",
        f"{AWAIR_UUID}_{SENSOR_TYPES_MAP[API_SCORE].unique_id_tag}",
        "88",
        {ATTR_ICON: "mdi:blur"},
    )

    with patch("python_awair.AwairClient.query", side_effect=OFFLINE_FIXTURE):
        await async_update_entity(hass, "sensor.living_room_awair_score")
        assert_expected_properties(
            hass,
            registry,
            "sensor.living_room_awair_score",
            f"{AWAIR_UUID}_{SENSOR_TYPES_MAP[API_SCORE].unique_id_tag}",
            STATE_UNAVAILABLE,
            {ATTR_ICON: "mdi:blur"},
        )
