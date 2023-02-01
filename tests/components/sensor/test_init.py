"""The test for sensor entity."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.sensor import (
    DEVICE_CLASS_UNITS,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    PERCENTAGE,
    STATE_UNKNOWN,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfMass,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfVolume,
    UnitOfVolumetricFlux,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.restore_state import STORAGE_KEY as RESTORE_STATE_KEY
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM

from tests.common import mock_restore_cache_with_extra_data


@pytest.mark.parametrize(
    "unit_system,native_unit,state_unit,native_value,state_value",
    [
        (
            US_CUSTOMARY_SYSTEM,
            UnitOfTemperature.FAHRENHEIT,
            UnitOfTemperature.FAHRENHEIT,
            100,
            "100",
        ),
        (
            US_CUSTOMARY_SYSTEM,
            UnitOfTemperature.CELSIUS,
            UnitOfTemperature.FAHRENHEIT,
            38,
            "100",
        ),
        (
            METRIC_SYSTEM,
            UnitOfTemperature.FAHRENHEIT,
            UnitOfTemperature.CELSIUS,
            100,
            "38",
        ),
        (
            METRIC_SYSTEM,
            UnitOfTemperature.CELSIUS,
            UnitOfTemperature.CELSIUS,
            38,
            "38",
        ),
    ],
)
async def test_temperature_conversion(
    hass,
    enable_custom_integrations,
    unit_system,
    native_unit,
    state_unit,
    native_value,
    state_value,
):
    """Test temperature conversion."""
    hass.config.units = unit_system
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test",
        native_value=str(native_value),
        native_unit_of_measurement=native_unit,
        device_class=SensorDeviceClass.TEMPERATURE,
    )

    entity0 = platform.ENTITIES["0"]
    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    state = hass.states.get(entity0.entity_id)
    assert state.state == state_value
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == state_unit


@pytest.mark.parametrize("device_class", (None, SensorDeviceClass.PRESSURE))
async def test_temperature_conversion_wrong_device_class(
    hass, device_class, enable_custom_integrations
):
    """Test temperatures are not converted if the sensor has wrong device class."""
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test",
        native_value="0.0",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=device_class,
    )

    entity0 = platform.ENTITIES["0"]
    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    # Check temperature is not converted
    state = hass.states.get(entity0.entity_id)
    assert state.state == "0.0"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfTemperature.FAHRENHEIT


@pytest.mark.parametrize("state_class", ("measurement", "total_increasing"))
async def test_deprecated_last_reset(
    hass, caplog, enable_custom_integrations, state_class
):
    """Test warning on deprecated last reset."""
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test", state_class=state_class, last_reset=dt_util.utc_from_timestamp(0)
    )

    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    assert (
        "Entity sensor.test (<class 'custom_components.test.sensor.MockSensor'>) "
        f"with state_class {state_class} has set last_reset. Setting last_reset for "
        "entities with state_class other than 'total' is not supported. Please update "
        "your configuration if state_class is manually configured, otherwise report it "
        "to the custom integration author."
    ) in caplog.text

    state = hass.states.get("sensor.test")
    assert "last_reset" not in state.attributes


async def test_datetime_conversion(hass, caplog, enable_custom_integrations):
    """Test conversion of datetime."""
    test_timestamp = datetime(2017, 12, 19, 18, 29, 42, tzinfo=timezone.utc)
    test_local_timestamp = test_timestamp.astimezone(
        dt_util.get_time_zone("Europe/Amsterdam")
    )
    test_date = date(2017, 12, 19)
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test",
        native_value=test_timestamp,
        device_class=SensorDeviceClass.TIMESTAMP,
    )
    platform.ENTITIES["1"] = platform.MockSensor(
        name="Test", native_value=test_date, device_class=SensorDeviceClass.DATE
    )
    platform.ENTITIES["2"] = platform.MockSensor(
        name="Test", native_value=None, device_class=SensorDeviceClass.TIMESTAMP
    )
    platform.ENTITIES["3"] = platform.MockSensor(
        name="Test", native_value=None, device_class=SensorDeviceClass.DATE
    )
    platform.ENTITIES["4"] = platform.MockSensor(
        name="Test",
        native_value=test_local_timestamp,
        device_class=SensorDeviceClass.TIMESTAMP,
    )

    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    state = hass.states.get(platform.ENTITIES["0"].entity_id)
    assert state.state == test_timestamp.isoformat()

    state = hass.states.get(platform.ENTITIES["1"].entity_id)
    assert state.state == test_date.isoformat()

    state = hass.states.get(platform.ENTITIES["2"].entity_id)
    assert state.state == STATE_UNKNOWN

    state = hass.states.get(platform.ENTITIES["3"].entity_id)
    assert state.state == STATE_UNKNOWN

    state = hass.states.get(platform.ENTITIES["4"].entity_id)
    assert state.state == test_timestamp.isoformat()


@pytest.mark.parametrize(
    "device_class,state_value,provides",
    [
        (SensorDeviceClass.DATE, "2021-01-09", "date"),
        (SensorDeviceClass.TIMESTAMP, "2021-01-09T12:00:00+00:00", "datetime"),
    ],
)
async def test_deprecated_datetime_str(
    hass, caplog, enable_custom_integrations, device_class, state_value, provides
):
    """Test warning on deprecated str for a date(time) value."""
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test", native_value=state_value, device_class=device_class
    )

    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    assert (
        f"Invalid {provides}: sensor.test has {device_class} device class "
        f"but provides state {state_value}:{type(state_value)}"
    ) in caplog.text


async def test_reject_timezoneless_datetime_str(
    hass, caplog, enable_custom_integrations
):
    """Test rejection of timezone-less datetime objects as timestamp."""
    test_timestamp = datetime(2017, 12, 19, 18, 29, 42, tzinfo=None)
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test",
        native_value=test_timestamp,
        device_class=SensorDeviceClass.TIMESTAMP,
    )

    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    assert (
        "Invalid datetime: sensor.test provides state '2017-12-19 18:29:42', "
        "which is missing timezone information"
    ) in caplog.text


RESTORE_DATA = {
    "str": {"native_unit_of_measurement": None, "native_value": "abc123"},
    "int": {"native_unit_of_measurement": "°F", "native_value": 123},
    "float": {"native_unit_of_measurement": "°F", "native_value": 123.0},
    "date": {
        "native_unit_of_measurement": None,
        "native_value": {
            "__type": "<class 'datetime.date'>",
            "isoformat": date(2020, 2, 8).isoformat(),
        },
    },
    "datetime": {
        "native_unit_of_measurement": None,
        "native_value": {
            "__type": "<class 'datetime.datetime'>",
            "isoformat": datetime(2020, 2, 8, 15, tzinfo=timezone.utc).isoformat(),
        },
    },
    "Decimal": {
        "native_unit_of_measurement": "kWh",
        "native_value": {
            "__type": "<class 'decimal.Decimal'>",
            "decimal_str": "123.4",
        },
    },
    "BadDecimal": {
        "native_unit_of_measurement": "°F",
        "native_value": {
            "__type": "<class 'decimal.Decimal'>",
            "decimal_str": "123f",
        },
    },
}


# None | str | int | float | date | datetime | Decimal:
@pytest.mark.parametrize(
    "native_value, native_value_type, expected_extra_data, device_class, uom",
    [
        ("abc123", str, RESTORE_DATA["str"], None, None),
        (
            123,
            int,
            RESTORE_DATA["int"],
            SensorDeviceClass.TEMPERATURE,
            UnitOfTemperature.FAHRENHEIT,
        ),
        (
            123.0,
            float,
            RESTORE_DATA["float"],
            SensorDeviceClass.TEMPERATURE,
            UnitOfTemperature.FAHRENHEIT,
        ),
        (date(2020, 2, 8), dict, RESTORE_DATA["date"], SensorDeviceClass.DATE, None),
        (
            datetime(2020, 2, 8, 15, tzinfo=timezone.utc),
            dict,
            RESTORE_DATA["datetime"],
            SensorDeviceClass.TIMESTAMP,
            None,
        ),
        (
            Decimal("123.4"),
            dict,
            RESTORE_DATA["Decimal"],
            SensorDeviceClass.ENERGY,
            UnitOfEnergy.KILO_WATT_HOUR,
        ),
    ],
)
async def test_restore_sensor_save_state(
    hass,
    enable_custom_integrations,
    hass_storage,
    native_value,
    native_value_type,
    expected_extra_data,
    device_class,
    uom,
):
    """Test RestoreSensor."""
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockRestoreSensor(
        name="Test",
        native_value=native_value,
        native_unit_of_measurement=uom,
        device_class=device_class,
    )

    entity0 = platform.ENTITIES["0"]
    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    # Trigger saving state
    await hass.async_stop()

    assert len(hass_storage[RESTORE_STATE_KEY]["data"]) == 1
    state = hass_storage[RESTORE_STATE_KEY]["data"][0]["state"]
    assert state["entity_id"] == entity0.entity_id
    extra_data = hass_storage[RESTORE_STATE_KEY]["data"][0]["extra_data"]
    assert extra_data == expected_extra_data
    assert type(extra_data["native_value"]) == native_value_type


@pytest.mark.parametrize(
    "native_value, native_value_type, extra_data, device_class, uom",
    [
        ("abc123", str, RESTORE_DATA["str"], None, None),
        (123, int, RESTORE_DATA["int"], SensorDeviceClass.TEMPERATURE, "°F"),
        (123.0, float, RESTORE_DATA["float"], SensorDeviceClass.TEMPERATURE, "°F"),
        (date(2020, 2, 8), date, RESTORE_DATA["date"], SensorDeviceClass.DATE, None),
        (
            datetime(2020, 2, 8, 15, tzinfo=timezone.utc),
            datetime,
            RESTORE_DATA["datetime"],
            SensorDeviceClass.TIMESTAMP,
            None,
        ),
        (
            Decimal("123.4"),
            Decimal,
            RESTORE_DATA["Decimal"],
            SensorDeviceClass.ENERGY,
            "kWh",
        ),
        (None, type(None), None, None, None),
        (None, type(None), {}, None, None),
        (None, type(None), {"beer": 123}, None, None),
        (
            None,
            type(None),
            {"native_unit_of_measurement": "°F", "native_value": {}},
            None,
            None,
        ),
        (None, type(None), RESTORE_DATA["BadDecimal"], SensorDeviceClass.ENERGY, None),
    ],
)
async def test_restore_sensor_restore_state(
    hass,
    enable_custom_integrations,
    hass_storage,
    native_value,
    native_value_type,
    extra_data,
    device_class,
    uom,
):
    """Test RestoreSensor."""
    mock_restore_cache_with_extra_data(hass, ((State("sensor.test", ""), extra_data),))

    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockRestoreSensor(
        name="Test",
        device_class=device_class,
    )

    entity0 = platform.ENTITIES["0"]
    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    assert hass.states.get(entity0.entity_id)

    assert entity0.native_value == native_value
    assert type(entity0.native_value) == native_value_type
    assert entity0.native_unit_of_measurement == uom


@pytest.mark.parametrize(
    "device_class, native_unit, custom_unit, state_unit, native_value, custom_state",
    [
        # Smaller to larger unit, InHg is ~33x larger than hPa -> 1 more decimal
        (
            SensorDeviceClass.PRESSURE,
            UnitOfPressure.HPA,
            UnitOfPressure.INHG,
            UnitOfPressure.INHG,
            1000.0,
            "29.53",
        ),
        (
            SensorDeviceClass.PRESSURE,
            UnitOfPressure.KPA,
            UnitOfPressure.HPA,
            UnitOfPressure.HPA,
            1.234,
            "12.340",
        ),
        (
            SensorDeviceClass.ATMOSPHERIC_PRESSURE,
            UnitOfPressure.HPA,
            UnitOfPressure.MMHG,
            UnitOfPressure.MMHG,
            1000,
            "750",
        ),
        (
            SensorDeviceClass.PRESSURE,
            UnitOfPressure.HPA,
            UnitOfPressure.MMHG,
            UnitOfPressure.MMHG,
            1000,
            "750",
        ),
        # Not a supported pressure unit
        (
            SensorDeviceClass.PRESSURE,
            UnitOfPressure.HPA,
            "peer_pressure",
            UnitOfPressure.HPA,
            1000,
            "1000",
        ),
        (
            SensorDeviceClass.TEMPERATURE,
            UnitOfTemperature.CELSIUS,
            UnitOfTemperature.FAHRENHEIT,
            UnitOfTemperature.FAHRENHEIT,
            37.5,
            "99.5",
        ),
        (
            SensorDeviceClass.TEMPERATURE,
            UnitOfTemperature.FAHRENHEIT,
            UnitOfTemperature.CELSIUS,
            UnitOfTemperature.CELSIUS,
            100,
            "38",
        ),
    ],
)
async def test_custom_unit(
    hass,
    enable_custom_integrations,
    device_class,
    native_unit,
    custom_unit,
    state_unit,
    native_value,
    custom_state,
):
    """Test custom unit."""
    entity_registry = er.async_get(hass)

    entry = entity_registry.async_get_or_create("sensor", "test", "very_unique")
    entity_registry.async_update_entity_options(
        entry.entity_id, "sensor", {"unit_of_measurement": custom_unit}
    )
    await hass.async_block_till_done()

    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test",
        native_value=str(native_value),
        native_unit_of_measurement=native_unit,
        device_class=device_class,
        unique_id="very_unique",
    )

    entity0 = platform.ENTITIES["0"]
    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    state = hass.states.get(entity0.entity_id)
    assert state.state == custom_state
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == state_unit


@pytest.mark.parametrize(
    "device_class,native_unit,custom_unit,native_value,native_precision,default_state,custom_state",
    [
        (
            SensorDeviceClass.ATMOSPHERIC_PRESSURE,
            UnitOfPressure.HPA,
            UnitOfPressure.INHG,
            1000.0,
            2,
            "1000.00",  # Native precision is 2
            "29.530",  # One digit of precision added when converting
        ),
        (
            SensorDeviceClass.ATMOSPHERIC_PRESSURE,
            UnitOfPressure.INHG,
            UnitOfPressure.HPA,
            29.9211,
            3,
            "29.921",  # Native precision is 3
            "1013.24",  # One digit of precision removed when converting
        ),
        (
            SensorDeviceClass.ATMOSPHERIC_PRESSURE,
            UnitOfPressure.INHG,
            UnitOfPressure.HPA,
            -0.0001,
            3,
            "0.000",  # Native precision is 3
            "0.00",  # One digit of precision removed when converting
        ),
    ],
)
async def test_native_precision_scaling(
    hass,
    enable_custom_integrations,
    device_class,
    native_unit,
    custom_unit,
    native_value,
    native_precision,
    default_state,
    custom_state,
):
    """Test native precision is influenced by unit conversion."""
    entity_registry = er.async_get(hass)

    entry = entity_registry.async_get_or_create("sensor", "test", "very_unique")
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test",
        native_value=str(native_value),
        native_precision=native_precision,
        native_unit_of_measurement=native_unit,
        device_class=device_class,
        unique_id="very_unique",
    )

    entity0 = platform.ENTITIES["0"]
    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    state = hass.states.get(entity0.entity_id)
    assert state.state == default_state
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == native_unit

    entity_registry.async_update_entity_options(
        entry.entity_id, "sensor", {"unit_of_measurement": custom_unit}
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity0.entity_id)
    assert state.state == custom_state
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == custom_unit


@pytest.mark.parametrize(
    "device_class,native_unit,custom_precision,native_value,default_state,custom_state",
    [
        (
            SensorDeviceClass.ATMOSPHERIC_PRESSURE,
            UnitOfPressure.HPA,
            4,
            1000.0,
            "1000.000",
            "1000.0000",
        ),
        (
            SensorDeviceClass.DISTANCE,
            UnitOfLength.KILOMETERS,
            1,
            -0.04,
            "-0.040",
            "0.0",  # Make sure minus is dropped
        ),
    ],
)
async def test_custom_precision_native_precision(
    hass,
    enable_custom_integrations,
    device_class,
    native_unit,
    custom_precision,
    native_value,
    default_state,
    custom_state,
):
    """Test custom precision."""
    entity_registry = er.async_get(hass)

    entry = entity_registry.async_get_or_create("sensor", "test", "very_unique")
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test",
        native_value=str(native_value),
        native_precision=3,
        native_unit_of_measurement=native_unit,
        device_class=device_class,
        unique_id="very_unique",
    )

    entity0 = platform.ENTITIES["0"]
    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    state = hass.states.get(entity0.entity_id)
    assert state.state == default_state
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == native_unit

    entity_registry.async_update_entity_options(
        entry.entity_id, "sensor", {"precision": custom_precision}
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity0.entity_id)
    assert state.state == custom_state
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == native_unit


@pytest.mark.parametrize(
    "device_class,native_unit,custom_precision,native_value,custom_state",
    [
        (
            SensorDeviceClass.ATMOSPHERIC_PRESSURE,
            UnitOfPressure.HPA,
            4,
            1000.0,
            "1000.0000",
        ),
    ],
)
async def test_custom_precision_no_native_precision(
    hass,
    enable_custom_integrations,
    device_class,
    native_unit,
    custom_precision,
    native_value,
    custom_state,
):
    """Test custom precision."""
    entity_registry = er.async_get(hass)

    entry = entity_registry.async_get_or_create("sensor", "test", "very_unique")
    entity_registry.async_update_entity_options(
        entry.entity_id, "sensor", {"precision": custom_precision}
    )
    await hass.async_block_till_done()

    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test",
        native_value=str(native_value),
        native_unit_of_measurement=native_unit,
        device_class=device_class,
        unique_id="very_unique",
    )

    entity0 = platform.ENTITIES["0"]
    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    state = hass.states.get(entity0.entity_id)
    assert state.state == custom_state
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == native_unit


@pytest.mark.parametrize(
    "native_unit, custom_unit, state_unit, native_value, native_state, custom_state, device_class",
    [
        # Distance
        (
            UnitOfLength.KILOMETERS,
            UnitOfLength.MILES,
            UnitOfLength.MILES,
            1000,
            "1000",
            "621",
            SensorDeviceClass.DISTANCE,
        ),
        (
            UnitOfLength.CENTIMETERS,
            UnitOfLength.INCHES,
            UnitOfLength.INCHES,
            7.24,
            "7.24",
            "2.85",
            SensorDeviceClass.DISTANCE,
        ),
        (
            UnitOfLength.KILOMETERS,
            "peer_distance",
            UnitOfLength.KILOMETERS,
            1000,
            "1000",
            "1000",
            SensorDeviceClass.DISTANCE,
        ),
        # Energy
        (
            UnitOfEnergy.KILO_WATT_HOUR,
            UnitOfEnergy.MEGA_WATT_HOUR,
            UnitOfEnergy.MEGA_WATT_HOUR,
            1000,
            "1000",
            "1.000",
            SensorDeviceClass.ENERGY,
        ),
        (
            UnitOfEnergy.GIGA_JOULE,
            UnitOfEnergy.MEGA_WATT_HOUR,
            UnitOfEnergy.MEGA_WATT_HOUR,
            1000,
            "1000",
            "278",
            SensorDeviceClass.ENERGY,
        ),
        (
            UnitOfEnergy.KILO_WATT_HOUR,
            "BTU",
            UnitOfEnergy.KILO_WATT_HOUR,
            1000,
            "1000",
            "1000",
            SensorDeviceClass.ENERGY,
        ),
        # Power factor
        (
            None,
            PERCENTAGE,
            PERCENTAGE,
            1.0,
            "1.0",
            "100.0",
            SensorDeviceClass.POWER_FACTOR,
        ),
        (
            PERCENTAGE,
            None,
            None,
            100,
            "100",
            "1.00",
            SensorDeviceClass.POWER_FACTOR,
        ),
        (
            "Cos φ",
            None,
            "Cos φ",
            1.0,
            "1.0",
            "1.0",
            SensorDeviceClass.POWER_FACTOR,
        ),
        # Pressure
        # Smaller to larger unit, InHg is ~33x larger than hPa -> 1 more decimal
        (
            UnitOfPressure.HPA,
            UnitOfPressure.INHG,
            UnitOfPressure.INHG,
            1000.0,
            "1000.0",
            "29.53",
            SensorDeviceClass.PRESSURE,
        ),
        (
            UnitOfPressure.KPA,
            UnitOfPressure.HPA,
            UnitOfPressure.HPA,
            1.234,
            "1.234",
            "12.340",
            SensorDeviceClass.PRESSURE,
        ),
        (
            UnitOfPressure.HPA,
            UnitOfPressure.MMHG,
            UnitOfPressure.MMHG,
            1000,
            "1000",
            "750",
            SensorDeviceClass.PRESSURE,
        ),
        # Not a supported pressure unit
        (
            UnitOfPressure.HPA,
            "peer_pressure",
            UnitOfPressure.HPA,
            1000,
            "1000",
            "1000",
            SensorDeviceClass.PRESSURE,
        ),
        # Speed
        (
            UnitOfSpeed.KILOMETERS_PER_HOUR,
            UnitOfSpeed.MILES_PER_HOUR,
            UnitOfSpeed.MILES_PER_HOUR,
            100,
            "100",
            "62",
            SensorDeviceClass.SPEED,
        ),
        (
            UnitOfVolumetricFlux.MILLIMETERS_PER_DAY,
            UnitOfVolumetricFlux.INCHES_PER_HOUR,
            UnitOfVolumetricFlux.INCHES_PER_HOUR,
            78,
            "78",
            "0.13",
            SensorDeviceClass.SPEED,
        ),
        (
            UnitOfSpeed.KILOMETERS_PER_HOUR,
            "peer_distance",
            UnitOfSpeed.KILOMETERS_PER_HOUR,
            100,
            "100",
            "100",
            SensorDeviceClass.SPEED,
        ),
        # Volume
        (
            UnitOfVolume.CUBIC_METERS,
            UnitOfVolume.CUBIC_FEET,
            UnitOfVolume.CUBIC_FEET,
            100,
            "100",
            "3531",
            SensorDeviceClass.VOLUME,
        ),
        (
            UnitOfVolume.LITERS,
            UnitOfVolume.FLUID_OUNCES,
            UnitOfVolume.FLUID_OUNCES,
            2.3,
            "2.3",
            "77.8",
            SensorDeviceClass.VOLUME,
        ),
        (
            UnitOfVolume.CUBIC_METERS,
            "peer_distance",
            UnitOfVolume.CUBIC_METERS,
            100,
            "100",
            "100",
            SensorDeviceClass.VOLUME,
        ),
        # Weight
        (
            UnitOfMass.GRAMS,
            UnitOfMass.OUNCES,
            UnitOfMass.OUNCES,
            100,
            "100",
            "3.5",
            SensorDeviceClass.WEIGHT,
        ),
        (
            UnitOfMass.OUNCES,
            UnitOfMass.GRAMS,
            UnitOfMass.GRAMS,
            78,
            "78",
            "2211",
            SensorDeviceClass.WEIGHT,
        ),
        (
            UnitOfMass.GRAMS,
            "peer_distance",
            UnitOfMass.GRAMS,
            100,
            "100",
            "100",
            SensorDeviceClass.WEIGHT,
        ),
    ],
)
async def test_custom_unit_change(
    hass,
    enable_custom_integrations,
    native_unit,
    custom_unit,
    state_unit,
    native_value,
    native_state,
    custom_state,
    device_class,
):
    """Test custom unit changes are picked up."""
    entity_registry = er.async_get(hass)
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test",
        native_value=str(native_value),
        native_unit_of_measurement=native_unit,
        device_class=device_class,
        unique_id="very_unique",
    )

    entity0 = platform.ENTITIES["0"]
    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    state = hass.states.get(entity0.entity_id)
    assert state.state == native_state
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == native_unit

    entity_registry.async_update_entity_options(
        "sensor.test", "sensor", {"unit_of_measurement": custom_unit}
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity0.entity_id)
    assert state.state == custom_state
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == state_unit

    entity_registry.async_update_entity_options(
        "sensor.test", "sensor", {"unit_of_measurement": native_unit}
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity0.entity_id)
    assert state.state == native_state
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == native_unit

    entity_registry.async_update_entity_options("sensor.test", "sensor", None)
    await hass.async_block_till_done()

    state = hass.states.get(entity0.entity_id)
    assert state.state == native_state
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == native_unit


@pytest.mark.parametrize(
    "unit_system, native_unit, automatic_unit, suggested_unit, custom_unit, native_value, native_state, automatic_state, suggested_state, custom_state, device_class",
    [
        # Distance
        (
            US_CUSTOMARY_SYSTEM,
            UnitOfLength.KILOMETERS,
            UnitOfLength.MILES,
            UnitOfLength.METERS,
            UnitOfLength.YARDS,
            1000,
            "1000",
            "621",
            "1000000",
            "1093613",
            SensorDeviceClass.DISTANCE,
        ),
    ],
)
async def test_unit_conversion_priority(
    hass,
    enable_custom_integrations,
    unit_system,
    native_unit,
    automatic_unit,
    suggested_unit,
    custom_unit,
    native_value,
    native_state,
    automatic_state,
    suggested_state,
    custom_state,
    device_class,
):
    """Test priority of unit conversion."""

    hass.config.units = unit_system

    entity_registry = er.async_get(hass)
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)

    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test",
        device_class=device_class,
        native_unit_of_measurement=native_unit,
        native_value=str(native_value),
        unique_id="very_unique",
    )
    entity0 = platform.ENTITIES["0"]

    platform.ENTITIES["1"] = platform.MockSensor(
        name="Test",
        device_class=device_class,
        native_unit_of_measurement=native_unit,
        native_value=str(native_value),
    )
    entity1 = platform.ENTITIES["1"]

    platform.ENTITIES["2"] = platform.MockSensor(
        name="Test",
        device_class=device_class,
        native_unit_of_measurement=native_unit,
        native_value=str(native_value),
        suggested_unit_of_measurement=suggested_unit,
        unique_id="very_unique_2",
    )
    entity2 = platform.ENTITIES["2"]

    platform.ENTITIES["3"] = platform.MockSensor(
        name="Test",
        device_class=device_class,
        native_unit_of_measurement=native_unit,
        native_value=str(native_value),
        suggested_unit_of_measurement=suggested_unit,
    )
    entity3 = platform.ENTITIES["3"]

    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    # Registered entity -> Follow automatic unit conversion
    state = hass.states.get(entity0.entity_id)
    assert state.state == automatic_state
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == automatic_unit
    # Assert the automatic unit conversion is stored in the registry
    entry = entity_registry.async_get(entity0.entity_id)
    assert entry.options == {
        "sensor.private": {"suggested_unit_of_measurement": automatic_unit}
    }

    # Unregistered entity -> Follow native unit
    state = hass.states.get(entity1.entity_id)
    assert state.state == native_state
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == native_unit

    # Registered entity with suggested unit
    state = hass.states.get(entity2.entity_id)
    assert state.state == suggested_state
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == suggested_unit
    # Assert the suggested unit is stored in the registry
    entry = entity_registry.async_get(entity2.entity_id)
    assert entry.options == {
        "sensor.private": {"suggested_unit_of_measurement": suggested_unit}
    }

    # Unregistered entity with suggested unit
    state = hass.states.get(entity3.entity_id)
    assert state.state == suggested_state
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == suggested_unit

    # Set a custom unit, this should have priority over the automatic unit conversion
    entity_registry.async_update_entity_options(
        entity0.entity_id, "sensor", {"unit_of_measurement": custom_unit}
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity0.entity_id)
    assert state.state == custom_state
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == custom_unit

    entity_registry.async_update_entity_options(
        entity2.entity_id, "sensor", {"unit_of_measurement": custom_unit}
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity2.entity_id)
    assert state.state == custom_state
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == custom_unit


@pytest.mark.parametrize(
    "unit_system, native_unit, original_unit, suggested_unit, native_value, original_value, device_class",
    [
        # Distance
        (
            US_CUSTOMARY_SYSTEM,
            UnitOfLength.KILOMETERS,
            UnitOfLength.YARDS,
            UnitOfLength.METERS,
            1000,
            1093613,
            SensorDeviceClass.DISTANCE,
        ),
    ],
)
async def test_unit_conversion_priority_suggested_unit_change(
    hass,
    enable_custom_integrations,
    unit_system,
    native_unit,
    original_unit,
    suggested_unit,
    native_value,
    original_value,
    device_class,
):
    """Test priority of unit conversion."""

    hass.config.units = unit_system

    entity_registry = er.async_get(hass)
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)

    # Pre-register entities
    entry = entity_registry.async_get_or_create("sensor", "test", "very_unique")
    entity_registry.async_update_entity_options(
        entry.entity_id,
        "sensor.private",
        {"suggested_unit_of_measurement": original_unit},
    )
    entry = entity_registry.async_get_or_create("sensor", "test", "very_unique_2")
    entity_registry.async_update_entity_options(
        entry.entity_id,
        "sensor.private",
        {"suggested_unit_of_measurement": original_unit},
    )

    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test",
        device_class=device_class,
        native_unit_of_measurement=native_unit,
        native_value=str(native_value),
        unique_id="very_unique",
    )
    entity0 = platform.ENTITIES["0"]

    platform.ENTITIES["1"] = platform.MockSensor(
        name="Test",
        device_class=device_class,
        native_unit_of_measurement=native_unit,
        native_value=str(native_value),
        suggested_unit_of_measurement=suggested_unit,
        unique_id="very_unique_2",
    )
    entity1 = platform.ENTITIES["1"]

    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    # Registered entity -> Follow automatic unit conversion the first time the entity was seen
    state = hass.states.get(entity0.entity_id)
    assert float(state.state) == pytest.approx(float(original_value))
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == original_unit

    # Registered entity -> Follow suggested unit the first time the entity was seen
    state = hass.states.get(entity1.entity_id)
    assert float(state.state) == pytest.approx(float(original_value))
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == original_unit


@pytest.mark.parametrize(
    "unit_system, native_unit, original_unit, native_value, original_value, device_class",
    [
        # Distance
        (
            US_CUSTOMARY_SYSTEM,
            UnitOfLength.KILOMETERS,
            UnitOfLength.MILES,
            1000,
            621.0,
            SensorDeviceClass.DISTANCE,
        ),
        (
            US_CUSTOMARY_SYSTEM,
            UnitOfLength.METERS,
            UnitOfLength.MILES,
            1000000,
            621.371,
            SensorDeviceClass.DISTANCE,
        ),
    ],
)
async def test_unit_conversion_priority_legacy_conversion_removed(
    hass,
    enable_custom_integrations,
    unit_system,
    native_unit,
    original_unit,
    native_value,
    original_value,
    device_class,
):
    """Test priority of unit conversion."""

    hass.config.units = unit_system

    entity_registry = er.async_get(hass)
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)

    # Pre-register entities
    entity_registry.async_get_or_create(
        "sensor", "test", "very_unique", unit_of_measurement=original_unit
    )

    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test",
        device_class=device_class,
        native_unit_of_measurement=native_unit,
        native_value=str(native_value),
        unique_id="very_unique",
    )
    entity0 = platform.ENTITIES["0"]

    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    state = hass.states.get(entity0.entity_id)
    assert float(state.state) == pytest.approx(float(original_value))
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == original_unit


def test_device_classes_aligned():
    """Make sure all number device classes are also available in SensorDeviceClass."""

    for device_class in NumberDeviceClass:
        assert hasattr(SensorDeviceClass, device_class.name)
        assert getattr(SensorDeviceClass, device_class.name).value == device_class.value


async def test_value_unknown_in_enumeration(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    enable_custom_integrations: None,
):
    """Test warning on invalid enum value."""
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test",
        native_value="invalid_option",
        device_class=SensorDeviceClass.ENUM,
        options=["option1", "option2"],
    )

    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    assert (
        "Sensor sensor.test provides state value 'invalid_option', "
        "which is not in the list of options provided"
    ) in caplog.text


async def test_invalid_enumeration_entity_with_device_class(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    enable_custom_integrations: None,
):
    """Test warning on entities that provide an enum with a device class."""
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test",
        native_value=21,
        device_class=SensorDeviceClass.POWER,
        options=["option1", "option2"],
    )

    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    assert (
        "Sensor sensor.test is providing enum options, but has device class 'power' "
        "instead of 'enum'"
    ) in caplog.text


async def test_invalid_enumeration_entity_without_device_class(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    enable_custom_integrations: None,
):
    """Test warning on entities that provide an enum without a device class."""
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test",
        native_value=21,
        options=["option1", "option2"],
    )

    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    assert (
        "Sensor sensor.test is providing enum options, but is missing "
        "the enum device class"
    ) in caplog.text


@pytest.mark.parametrize(
    "device_class",
    (
        SensorDeviceClass.DATE,
        SensorDeviceClass.ENUM,
        SensorDeviceClass.TIMESTAMP,
    ),
)
async def test_non_numeric_device_class_with_unit_of_measurement(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    enable_custom_integrations: None,
    device_class: SensorDeviceClass,
):
    """Test error on numeric entities that provide an unit of measurement."""
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test",
        native_value=None,
        device_class=device_class,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        options=["option1", "option2"],
    )

    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    assert (
        "Sensor sensor.test has a unit of measurement and thus indicating it has "
        f"a numeric value; however, it has the non-numeric device class: {device_class}"
    ) in caplog.text


@pytest.mark.parametrize(
    "device_class",
    (
        SensorDeviceClass.APPARENT_POWER,
        SensorDeviceClass.AQI,
        SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        SensorDeviceClass.BATTERY,
        SensorDeviceClass.CO,
        SensorDeviceClass.CO2,
        SensorDeviceClass.CURRENT,
        SensorDeviceClass.DATA_RATE,
        SensorDeviceClass.DATA_SIZE,
        SensorDeviceClass.DISTANCE,
        SensorDeviceClass.DURATION,
        SensorDeviceClass.ENERGY,
        SensorDeviceClass.FREQUENCY,
        SensorDeviceClass.GAS,
        SensorDeviceClass.HUMIDITY,
        SensorDeviceClass.ILLUMINANCE,
        SensorDeviceClass.IRRADIANCE,
        SensorDeviceClass.MOISTURE,
        SensorDeviceClass.NITROGEN_DIOXIDE,
        SensorDeviceClass.NITROGEN_MONOXIDE,
        SensorDeviceClass.NITROUS_OXIDE,
        SensorDeviceClass.OZONE,
        SensorDeviceClass.PM1,
        SensorDeviceClass.PM10,
        SensorDeviceClass.PM25,
        SensorDeviceClass.POWER_FACTOR,
        SensorDeviceClass.POWER,
        SensorDeviceClass.PRECIPITATION_INTENSITY,
        SensorDeviceClass.PRECIPITATION,
        SensorDeviceClass.PRESSURE,
        SensorDeviceClass.REACTIVE_POWER,
        SensorDeviceClass.SIGNAL_STRENGTH,
        SensorDeviceClass.SOUND_PRESSURE,
        SensorDeviceClass.SPEED,
        SensorDeviceClass.SULPHUR_DIOXIDE,
        SensorDeviceClass.TEMPERATURE,
        SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
        SensorDeviceClass.VOLTAGE,
        SensorDeviceClass.VOLUME,
        SensorDeviceClass.WATER,
        SensorDeviceClass.WEIGHT,
        SensorDeviceClass.WIND_SPEED,
    ),
)
async def test_device_classes_with_invalid_unit_of_measurement(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    enable_custom_integrations: None,
    device_class: SensorDeviceClass,
):
    """Test error when unit of measurement is not valid for used device class."""
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test",
        native_value="1.0",
        device_class=device_class,
        native_unit_of_measurement="INVALID!",
    )
    units = [
        str(unit) if unit else "no unit of measurement"
        for unit in DEVICE_CLASS_UNITS.get(device_class, set())
    ]
    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    assert (
        "is using native unit of measurement 'INVALID!' which is not a valid "
        f"unit for the device class ('{device_class}') it is using; "
        f"expected one of {units}"
    ) in caplog.text


@pytest.mark.parametrize(
    "device_class,state_class,unit",
    [
        (SensorDeviceClass.AQI, None, None),
        (None, SensorStateClass.MEASUREMENT, None),
        (None, None, UnitOfTemperature.CELSIUS),
    ],
)
@pytest.mark.parametrize(
    "native_value,expected",
    [
        ("abc", "abc"),
        ("13.7.1", "13.7.1"),
        (datetime(2012, 11, 10, 7, 35, 1), "2012-11-10 07:35:01"),
        (date(2012, 11, 10), "2012-11-10"),
    ],
)
async def test_non_numeric_validation_warn(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    enable_custom_integrations: None,
    native_value: Any,
    expected: str,
    device_class: SensorDeviceClass | None,
    state_class: SensorStateClass | None,
    unit: str | None,
) -> None:
    """Test error on expected numeric entities."""
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test",
        native_value=native_value,
        device_class=device_class,
        native_unit_of_measurement=unit,
        state_class=state_class,
    )
    entity0 = platform.ENTITIES["0"]

    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    state = hass.states.get(entity0.entity_id)
    assert state.state == expected

    assert (
        "thus indicating it has a numeric value; "
        f"however, it has the non-numeric value: {native_value}"
    ) in caplog.text


@pytest.mark.parametrize(
    "device_class,state_class,unit,precision", ((None, None, None, 1),)
)
@pytest.mark.parametrize(
    "native_value,expected",
    [
        ("abc", "abc"),
        ("13.7.1", "13.7.1"),
        (datetime(2012, 11, 10, 7, 35, 1), "2012-11-10 07:35:01"),
        (date(2012, 11, 10), "2012-11-10"),
    ],
)
async def test_non_numeric_validation_raise(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    enable_custom_integrations: None,
    native_value: Any,
    expected: str,
    device_class: SensorDeviceClass | None,
    state_class: SensorStateClass | None,
    unit: str | None,
    precision,
) -> None:
    """Test error on expected numeric entities."""
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test",
        device_class=device_class,
        native_precision=precision,
        native_unit_of_measurement=unit,
        native_value=native_value,
        state_class=state_class,
    )
    entity0 = platform.ENTITIES["0"]

    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    state = hass.states.get(entity0.entity_id)
    assert state is None

    assert ("Error adding entities for domain sensor with platform test") in caplog.text


@pytest.mark.parametrize(
    "device_class,state_class,unit",
    [
        (SensorDeviceClass.AQI, None, None),
        (None, SensorStateClass.MEASUREMENT, None),
        (None, None, UnitOfTemperature.CELSIUS),
    ],
)
@pytest.mark.parametrize(
    "native_value,expected",
    [
        (13, "13"),
        (17.50, "17.5"),
        (Decimal(18.50), "18.5"),
        ("19.70", "19.70"),
        (None, STATE_UNKNOWN),
    ],
)
async def test_numeric_validation(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    enable_custom_integrations: None,
    native_value: Any,
    expected: str,
    device_class: SensorDeviceClass | None,
    state_class: SensorStateClass | None,
    unit: str | None,
) -> None:
    """Test does not error on expected numeric entities."""
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test",
        native_value=native_value,
        device_class=device_class,
        native_unit_of_measurement=unit,
        state_class=state_class,
    )
    entity0 = platform.ENTITIES["0"]

    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    state = hass.states.get(entity0.entity_id)
    assert state.state == expected

    assert (
        "thus indicating it has a numeric value; "
        f"however, it has the non-numeric value: {native_value}"
    ) not in caplog.text


async def test_numeric_validation_ignores_custom_device_class(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    enable_custom_integrations: None,
) -> None:
    """Test does not error on expected numeric entities."""
    native_value = "Three elephants"
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test",
        native_value=native_value,
        device_class="custom__deviceclass",
    )
    entity0 = platform.ENTITIES["0"]

    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    state = hass.states.get(entity0.entity_id)
    assert state.state == "Three elephants"

    assert (
        "thus indicating it has a numeric value; "
        f"however, it has the non-numeric value: {native_value}"
    ) not in caplog.text


@pytest.mark.parametrize(
    "device_class",
    list(SensorDeviceClass),
)
async def test_device_classes_with_invalid_state_class(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    enable_custom_integrations: None,
    device_class: SensorDeviceClass,
):
    """Test error when unit of measurement is not valid for used device class."""
    platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    platform.ENTITIES["0"] = platform.MockSensor(
        name="Test",
        native_value=None,
        state_class="INVALID!",
        device_class=device_class,
    )

    assert await async_setup_component(hass, "sensor", {"sensor": {"platform": "test"}})
    await hass.async_block_till_done()

    assert (
        "is using state class 'INVALID!' which is impossible considering device "
        f"class ('{device_class}') it is using"
    ) in caplog.text
