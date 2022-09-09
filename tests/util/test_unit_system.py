"""Test the unit system helper."""
import pytest

from homeassistant.const import (
    ACCUMULATED_PRECIPITATION,
    LENGTH,
    LENGTH_KILOMETERS,
    LENGTH_METERS,
    LENGTH_MILLIMETERS,
    MASS,
    MASS_GRAMS,
    PRESSURE,
    PRESSURE_PA,
    SPEED_METERS_PER_SECOND,
    TEMP_CELSIUS,
    TEMPERATURE,
    VOLUME,
    VOLUME_LITERS,
    WIND_SPEED,
)
from homeassistant.util.unit_system import IMPERIAL_SYSTEM, METRIC_SYSTEM, UnitSystem

SYSTEM_NAME = "TEST"
INVALID_UNIT = "INVALID"


def test_invalid_units():
    """Test errors are raised when invalid units are passed in."""
    with pytest.raises(ValueError):
        UnitSystem(
            SYSTEM_NAME,
            INVALID_UNIT,
            LENGTH_METERS,
            SPEED_METERS_PER_SECOND,
            VOLUME_LITERS,
            MASS_GRAMS,
            PRESSURE_PA,
            LENGTH_MILLIMETERS,
        )

    with pytest.raises(ValueError):
        UnitSystem(
            SYSTEM_NAME,
            TEMP_CELSIUS,
            INVALID_UNIT,
            SPEED_METERS_PER_SECOND,
            VOLUME_LITERS,
            MASS_GRAMS,
            PRESSURE_PA,
            LENGTH_MILLIMETERS,
        )

    with pytest.raises(ValueError):
        UnitSystem(
            SYSTEM_NAME,
            TEMP_CELSIUS,
            LENGTH_METERS,
            INVALID_UNIT,
            VOLUME_LITERS,
            MASS_GRAMS,
            PRESSURE_PA,
            LENGTH_MILLIMETERS,
        )

    with pytest.raises(ValueError):
        UnitSystem(
            SYSTEM_NAME,
            TEMP_CELSIUS,
            LENGTH_METERS,
            SPEED_METERS_PER_SECOND,
            INVALID_UNIT,
            MASS_GRAMS,
            PRESSURE_PA,
            LENGTH_MILLIMETERS,
        )

    with pytest.raises(ValueError):
        UnitSystem(
            SYSTEM_NAME,
            TEMP_CELSIUS,
            LENGTH_METERS,
            SPEED_METERS_PER_SECOND,
            VOLUME_LITERS,
            INVALID_UNIT,
            PRESSURE_PA,
            LENGTH_MILLIMETERS,
        )

    with pytest.raises(ValueError):
        UnitSystem(
            SYSTEM_NAME,
            TEMP_CELSIUS,
            LENGTH_METERS,
            SPEED_METERS_PER_SECOND,
            VOLUME_LITERS,
            MASS_GRAMS,
            INVALID_UNIT,
            LENGTH_MILLIMETERS,
        )

    with pytest.raises(ValueError):
        UnitSystem(
            SYSTEM_NAME,
            TEMP_CELSIUS,
            LENGTH_METERS,
            SPEED_METERS_PER_SECOND,
            VOLUME_LITERS,
            MASS_GRAMS,
            PRESSURE_PA,
            INVALID_UNIT,
        )


def test_invalid_value():
    """Test no conversion happens if value is non-numeric."""
    with pytest.raises(TypeError):
        METRIC_SYSTEM.length("25a", LENGTH_KILOMETERS)
    with pytest.raises(TypeError):
        METRIC_SYSTEM.temperature("50K", TEMP_CELSIUS)
    with pytest.raises(TypeError):
        METRIC_SYSTEM.wind_speed("50km/h", SPEED_METERS_PER_SECOND)
    with pytest.raises(TypeError):
        METRIC_SYSTEM.volume("50L", VOLUME_LITERS)
    with pytest.raises(TypeError):
        METRIC_SYSTEM.pressure("50Pa", PRESSURE_PA)
    with pytest.raises(TypeError):
        METRIC_SYSTEM.accumulated_precipitation("50mm", LENGTH_MILLIMETERS)


def test_as_dict():
    """Test that the as_dict() method returns the expected dictionary."""
    expected = {
        LENGTH: LENGTH_KILOMETERS,
        WIND_SPEED: SPEED_METERS_PER_SECOND,
        TEMPERATURE: TEMP_CELSIUS,
        VOLUME: VOLUME_LITERS,
        MASS: MASS_GRAMS,
        PRESSURE: PRESSURE_PA,
        ACCUMULATED_PRECIPITATION: LENGTH_MILLIMETERS,
    }

    assert expected == METRIC_SYSTEM.as_dict()


def test_temperature_same_unit():
    """Test no conversion happens if to unit is same as from unit."""
    assert METRIC_SYSTEM.temperature(5, METRIC_SYSTEM.temperature_unit) == 5


def test_temperature_unknown_unit():
    """Test no conversion happens if unknown unit."""
    with pytest.raises(ValueError):
        METRIC_SYSTEM.temperature(5, "abc")


def test_temperature_to_metric():
    """Test temperature conversion to metric system."""
    assert METRIC_SYSTEM.temperature(25, METRIC_SYSTEM.temperature_unit) == 25
    assert (
        round(METRIC_SYSTEM.temperature(80, IMPERIAL_SYSTEM.temperature_unit), 1)
        == 26.7
    )


def test_temperature_to_imperial():
    """Test temperature conversion to imperial system."""
    assert IMPERIAL_SYSTEM.temperature(77, IMPERIAL_SYSTEM.temperature_unit) == 77
    assert IMPERIAL_SYSTEM.temperature(25, METRIC_SYSTEM.temperature_unit) == 77


def test_length_unknown_unit():
    """Test length conversion with unknown from unit."""
    with pytest.raises(ValueError):
        METRIC_SYSTEM.length(5, "fr")


def test_length_to_metric():
    """Test length conversion to metric system."""
    assert METRIC_SYSTEM.length(100, METRIC_SYSTEM.length_unit) == 100
    assert METRIC_SYSTEM.length(5, IMPERIAL_SYSTEM.length_unit) == pytest.approx(
        8.04672
    )


def test_length_to_imperial():
    """Test length conversion to imperial system."""
    assert IMPERIAL_SYSTEM.length(100, IMPERIAL_SYSTEM.length_unit) == 100
    assert IMPERIAL_SYSTEM.length(5, METRIC_SYSTEM.length_unit) == pytest.approx(
        3.106855
    )


def test_wind_speed_unknown_unit():
    """Test wind_speed conversion with unknown from unit."""
    with pytest.raises(ValueError):
        METRIC_SYSTEM.length(5, "turtles")


def test_wind_speed_to_metric():
    """Test length conversion to metric system."""
    assert METRIC_SYSTEM.wind_speed(100, METRIC_SYSTEM.wind_speed_unit) == 100
    # 1 m/s is about 2.237 mph
    assert METRIC_SYSTEM.wind_speed(
        2237, IMPERIAL_SYSTEM.wind_speed_unit
    ) == pytest.approx(1000, abs=0.1)


def test_wind_speed_to_imperial():
    """Test wind_speed conversion to imperial system."""
    assert IMPERIAL_SYSTEM.wind_speed(100, IMPERIAL_SYSTEM.wind_speed_unit) == 100
    assert IMPERIAL_SYSTEM.wind_speed(
        1000, METRIC_SYSTEM.wind_speed_unit
    ) == pytest.approx(2237, abs=0.1)


def test_pressure_same_unit():
    """Test no conversion happens if to unit is same as from unit."""
    assert METRIC_SYSTEM.pressure(5, METRIC_SYSTEM.pressure_unit) == 5


def test_pressure_unknown_unit():
    """Test no conversion happens if unknown unit."""
    with pytest.raises(ValueError):
        METRIC_SYSTEM.pressure(5, "K")


def test_pressure_to_metric():
    """Test pressure conversion to metric system."""
    assert METRIC_SYSTEM.pressure(25, METRIC_SYSTEM.pressure_unit) == 25
    assert METRIC_SYSTEM.pressure(14.7, IMPERIAL_SYSTEM.pressure_unit) == pytest.approx(
        101352.932, abs=1e-1
    )


def test_pressure_to_imperial():
    """Test pressure conversion to imperial system."""
    assert IMPERIAL_SYSTEM.pressure(77, IMPERIAL_SYSTEM.pressure_unit) == 77
    assert IMPERIAL_SYSTEM.pressure(
        101352.932, METRIC_SYSTEM.pressure_unit
    ) == pytest.approx(14.7, abs=1e-4)


def test_accumulated_precipitation_same_unit():
    """Test no conversion happens if to unit is same as from unit."""
    assert (
        METRIC_SYSTEM.accumulated_precipitation(
            5, METRIC_SYSTEM.accumulated_precipitation_unit
        )
        == 5
    )


def test_accumulated_precipitation_unknown_unit():
    """Test no conversion happens if unknown unit."""
    with pytest.raises(ValueError):
        METRIC_SYSTEM.accumulated_precipitation(5, "K")


def test_accumulated_precipitation_to_metric():
    """Test accumulated_precipitation conversion to metric system."""
    assert (
        METRIC_SYSTEM.accumulated_precipitation(
            25, METRIC_SYSTEM.accumulated_precipitation_unit
        )
        == 25
    )
    assert METRIC_SYSTEM.accumulated_precipitation(
        10, IMPERIAL_SYSTEM.accumulated_precipitation_unit
    ) == pytest.approx(254, abs=1e-4)


def test_accumulated_precipitation_to_imperial():
    """Test accumulated_precipitation conversion to imperial system."""
    assert (
        IMPERIAL_SYSTEM.accumulated_precipitation(
            10, IMPERIAL_SYSTEM.accumulated_precipitation_unit
        )
        == 10
    )
    assert IMPERIAL_SYSTEM.accumulated_precipitation(
        254, METRIC_SYSTEM.accumulated_precipitation_unit
    ) == pytest.approx(10, abs=1e-4)


def test_properties():
    """Test the unit properties are returned as expected."""
    assert METRIC_SYSTEM.length_unit == LENGTH_KILOMETERS
    assert METRIC_SYSTEM.wind_speed_unit == SPEED_METERS_PER_SECOND
    assert METRIC_SYSTEM.temperature_unit == TEMP_CELSIUS
    assert METRIC_SYSTEM.mass_unit == MASS_GRAMS
    assert METRIC_SYSTEM.volume_unit == VOLUME_LITERS
    assert METRIC_SYSTEM.pressure_unit == PRESSURE_PA
    assert METRIC_SYSTEM.accumulated_precipitation_unit == LENGTH_MILLIMETERS


def test_is_metric():
    """Test the is metric flag."""
    assert METRIC_SYSTEM.is_metric
    assert not IMPERIAL_SYSTEM.is_metric
