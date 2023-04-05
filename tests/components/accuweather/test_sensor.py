"""Test sensor of AccuWeather integration."""
from datetime import timedelta
from unittest.mock import PropertyMock, patch

from homeassistant.components.accuweather.const import ATTRIBUTION, DOMAIN
from homeassistant.components.sensor import (
    ATTR_OPTIONS,
    ATTR_STATE_CLASS,
    DOMAIN as SENSOR_DOMAIN,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_DEVICE_CLASS,
    ATTR_ENTITY_ID,
    ATTR_ICON,
    ATTR_UNIT_OF_MEASUREMENT,
    CONCENTRATION_PARTS_PER_CUBIC_METER,
    PERCENTAGE,
    STATE_UNAVAILABLE,
    UV_INDEX,
    UnitOfLength,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumetricFlux,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util.dt import utcnow
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from . import init_integration

from tests.common import (
    async_fire_time_changed,
    load_json_array_fixture,
    load_json_object_fixture,
)


async def test_sensor_without_forecast(hass: HomeAssistant) -> None:
    """Test states of the sensor without forecast."""
    await init_integration(hass)
    registry = er.async_get(hass)

    state = hass.states.get("sensor.home_cloud_ceiling")
    assert state
    assert state.state == "3200.0"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert state.attributes.get(ATTR_ICON) == "mdi:weather-fog"
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfLength.METERS
    assert state.attributes.get(ATTR_STATE_CLASS) == SensorStateClass.MEASUREMENT
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.DISTANCE

    entry = registry.async_get("sensor.home_cloud_ceiling")
    assert entry
    assert entry.unique_id == "0123456-ceiling"
    assert entry.options["sensor"] == {"suggested_display_precision": 0}

    state = hass.states.get("sensor.home_precipitation")
    assert state
    assert state.state == "0.0"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert (
        state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        == UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR
    )
    assert state.attributes.get(ATTR_ICON) is None
    assert state.attributes.get("type") is None
    assert state.attributes.get(ATTR_STATE_CLASS) == SensorStateClass.MEASUREMENT
    assert (
        state.attributes.get(ATTR_DEVICE_CLASS)
        == SensorDeviceClass.PRECIPITATION_INTENSITY
    )

    entry = registry.async_get("sensor.home_precipitation")
    assert entry
    assert entry.unique_id == "0123456-precipitation"

    state = hass.states.get("sensor.home_pressure_tendency")
    assert state
    assert state.state == "falling"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert state.attributes.get(ATTR_ICON) == "mdi:gauge"
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.ENUM
    assert state.attributes.get(ATTR_STATE_CLASS) is None
    assert state.attributes.get(ATTR_OPTIONS) == ["falling", "rising", "steady"]

    entry = registry.async_get("sensor.home_pressure_tendency")
    assert entry
    assert entry.unique_id == "0123456-pressuretendency"
    assert entry.translation_key == "pressure_tendency"

    state = hass.states.get("sensor.home_realfeel_temperature")
    assert state
    assert state.state == "25.1"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfTemperature.CELSIUS
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.TEMPERATURE
    assert state.attributes.get(ATTR_STATE_CLASS) == SensorStateClass.MEASUREMENT

    entry = registry.async_get("sensor.home_realfeel_temperature")
    assert entry
    assert entry.unique_id == "0123456-realfeeltemperature"

    state = hass.states.get("sensor.home_uv_index")
    assert state
    assert state.state == "6"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UV_INDEX
    assert state.attributes.get("level") == "High"
    assert state.attributes.get(ATTR_STATE_CLASS) == SensorStateClass.MEASUREMENT

    entry = registry.async_get("sensor.home_uv_index")
    assert entry
    assert entry.unique_id == "0123456-uvindex"


async def test_sensor_with_forecast(hass: HomeAssistant) -> None:
    """Test states of the sensor with forecast."""
    await init_integration(hass, forecast=True)
    registry = er.async_get(hass)

    state = hass.states.get("sensor.home_hours_of_sun_0d")
    assert state
    assert state.state == "7.2"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert state.attributes.get(ATTR_ICON) == "mdi:weather-partly-cloudy"
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfTime.HOURS
    assert state.attributes.get(ATTR_STATE_CLASS) is None

    entry = registry.async_get("sensor.home_hours_of_sun_0d")
    assert entry
    assert entry.unique_id == "0123456-hoursofsun-0"

    state = hass.states.get("sensor.home_realfeel_temperature_max_0d")
    assert state
    assert state.state == "29.8"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfTemperature.CELSIUS
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.TEMPERATURE
    assert state.attributes.get(ATTR_STATE_CLASS) is None

    entry = registry.async_get("sensor.home_realfeel_temperature_max_0d")
    assert entry

    state = hass.states.get("sensor.home_realfeel_temperature_min_0d")
    assert state
    assert state.state == "15.1"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfTemperature.CELSIUS
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.TEMPERATURE
    assert state.attributes.get(ATTR_STATE_CLASS) is None

    entry = registry.async_get("sensor.home_realfeel_temperature_min_0d")
    assert entry
    assert entry.unique_id == "0123456-realfeeltemperaturemin-0"

    state = hass.states.get("sensor.home_thunderstorm_probability_day_0d")
    assert state
    assert state.state == "40"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert state.attributes.get(ATTR_ICON) == "mdi:weather-lightning"
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == PERCENTAGE
    assert state.attributes.get(ATTR_STATE_CLASS) is None

    entry = registry.async_get("sensor.home_thunderstorm_probability_day_0d")
    assert entry
    assert entry.unique_id == "0123456-thunderstormprobabilityday-0"

    state = hass.states.get("sensor.home_thunderstorm_probability_night_0d")
    assert state
    assert state.state == "40"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert state.attributes.get(ATTR_ICON) == "mdi:weather-lightning"
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == PERCENTAGE
    assert state.attributes.get(ATTR_STATE_CLASS) is None

    entry = registry.async_get("sensor.home_thunderstorm_probability_night_0d")
    assert entry
    assert entry.unique_id == "0123456-thunderstormprobabilitynight-0"

    state = hass.states.get("sensor.home_uv_index_0d")
    assert state
    assert state.state == "5"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert state.attributes.get(ATTR_ICON) == "mdi:weather-sunny"
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UV_INDEX
    assert state.attributes.get("level") == "Moderate"
    assert state.attributes.get(ATTR_STATE_CLASS) is None

    entry = registry.async_get("sensor.home_uv_index_0d")
    assert entry
    assert entry.unique_id == "0123456-uvindex-0"


async def test_sensor_disabled(hass: HomeAssistant) -> None:
    """Test sensor disabled by default."""
    await init_integration(hass)
    registry = er.async_get(hass)

    entry = registry.async_get("sensor.home_apparent_temperature")
    assert entry
    assert entry.unique_id == "0123456-apparenttemperature"
    assert entry.disabled
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION

    # Test enabling entity
    updated_entry = registry.async_update_entity(
        entry.entity_id, **{"disabled_by": None}
    )

    assert updated_entry != entry
    assert updated_entry.disabled is False


async def test_sensor_enabled_without_forecast(hass: HomeAssistant) -> None:
    """Test enabling an advanced sensor."""
    registry = er.async_get(hass)

    registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "0123456-apparenttemperature",
        suggested_object_id="home_apparent_temperature",
        disabled_by=None,
    )
    registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "0123456-cloudcover",
        suggested_object_id="home_cloud_cover",
        disabled_by=None,
    )
    registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "0123456-dewpoint",
        suggested_object_id="home_dew_point",
        disabled_by=None,
    )
    registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "0123456-realfeeltemperatureshade",
        suggested_object_id="home_realfeel_temperature_shade",
        disabled_by=None,
    )
    registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "0123456-wetbulbtemperature",
        suggested_object_id="home_wet_bulb_temperature",
        disabled_by=None,
    )
    registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "0123456-wind",
        suggested_object_id="home_wind",
        disabled_by=None,
    )
    registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "0123456-windchilltemperature",
        suggested_object_id="home_wind_chill_temperature",
        disabled_by=None,
    )
    registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "0123456-windgust",
        suggested_object_id="home_wind_gust",
        disabled_by=None,
    )
    registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "0123456-cloudcoverday-0",
        suggested_object_id="home_cloud_cover_day_0d",
        disabled_by=None,
    )
    registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "0123456-cloudcovernight-0",
        suggested_object_id="home_cloud_cover_night_0d",
        disabled_by=None,
    )
    registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "0123456-grass-0",
        suggested_object_id="home_grass_pollen_0d",
        disabled_by=None,
    )
    registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "0123456-mold-0",
        suggested_object_id="home_mold_pollen_0d",
        disabled_by=None,
    )
    registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "0123456-ozone-0",
        suggested_object_id="home_ozone_0d",
        disabled_by=None,
    )
    registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "0123456-ragweed-0",
        suggested_object_id="home_ragweed_pollen_0d",
        disabled_by=None,
    )
    registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "0123456-realfeeltemperatureshademax-0",
        suggested_object_id="home_realfeel_temperature_shade_max_0d",
        disabled_by=None,
    )
    registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "0123456-realfeeltemperatureshademin-0",
        suggested_object_id="home_realfeel_temperature_shade_min_0d",
        disabled_by=None,
    )
    registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "0123456-tree-0",
        suggested_object_id="home_tree_pollen_0d",
        disabled_by=None,
    )
    registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "0123456-windgustday-0",
        suggested_object_id="home_wind_gust_day_0d",
        disabled_by=None,
    )
    registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "0123456-windgustnight-0",
        suggested_object_id="home_wind_gust_night_0d",
        disabled_by=None,
    )
    registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "0123456-windday-0",
        suggested_object_id="home_wind_day_0d",
        disabled_by=None,
    )
    registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "0123456-windnight-0",
        suggested_object_id="home_wind_night_0d",
        disabled_by=None,
    )

    await init_integration(hass, forecast=True)

    state = hass.states.get("sensor.home_apparent_temperature")
    assert state
    assert state.state == "22.8"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfTemperature.CELSIUS
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.TEMPERATURE
    assert state.attributes.get(ATTR_STATE_CLASS) == SensorStateClass.MEASUREMENT

    entry = registry.async_get("sensor.home_apparent_temperature")
    assert entry
    assert entry.unique_id == "0123456-apparenttemperature"

    state = hass.states.get("sensor.home_cloud_cover")
    assert state
    assert state.state == "10"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == PERCENTAGE
    assert state.attributes.get(ATTR_ICON) == "mdi:weather-cloudy"
    assert state.attributes.get(ATTR_STATE_CLASS) == SensorStateClass.MEASUREMENT

    entry = registry.async_get("sensor.home_cloud_cover")
    assert entry
    assert entry.unique_id == "0123456-cloudcover"

    state = hass.states.get("sensor.home_dew_point")
    assert state
    assert state.state == "16.2"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfTemperature.CELSIUS
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.TEMPERATURE
    assert state.attributes.get(ATTR_STATE_CLASS) == SensorStateClass.MEASUREMENT

    entry = registry.async_get("sensor.home_dew_point")
    assert entry
    assert entry.unique_id == "0123456-dewpoint"

    state = hass.states.get("sensor.home_realfeel_temperature_shade")
    assert state
    assert state.state == "21.1"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfTemperature.CELSIUS
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.TEMPERATURE
    assert state.attributes.get(ATTR_STATE_CLASS) == SensorStateClass.MEASUREMENT

    entry = registry.async_get("sensor.home_realfeel_temperature_shade")
    assert entry
    assert entry.unique_id == "0123456-realfeeltemperatureshade"

    state = hass.states.get("sensor.home_wet_bulb_temperature")
    assert state
    assert state.state == "18.6"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfTemperature.CELSIUS
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.TEMPERATURE
    assert state.attributes.get(ATTR_STATE_CLASS) == SensorStateClass.MEASUREMENT

    entry = registry.async_get("sensor.home_wet_bulb_temperature")
    assert entry
    assert entry.unique_id == "0123456-wetbulbtemperature"

    state = hass.states.get("sensor.home_wind_chill_temperature")
    assert state
    assert state.state == "22.8"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfTemperature.CELSIUS
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.TEMPERATURE
    assert state.attributes.get(ATTR_STATE_CLASS) == SensorStateClass.MEASUREMENT

    entry = registry.async_get("sensor.home_wind_chill_temperature")
    assert entry
    assert entry.unique_id == "0123456-windchilltemperature"

    state = hass.states.get("sensor.home_wind_gust")
    assert state
    assert state.state == "20.3"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert (
        state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        == UnitOfSpeed.KILOMETERS_PER_HOUR
    )
    assert state.attributes.get(ATTR_ICON) is None
    assert state.attributes.get(ATTR_STATE_CLASS) == SensorStateClass.MEASUREMENT
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.WIND_SPEED

    entry = registry.async_get("sensor.home_wind_gust")
    assert entry
    assert entry.unique_id == "0123456-windgust"

    state = hass.states.get("sensor.home_wind")
    assert state
    assert state.state == "14.5"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert (
        state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        == UnitOfSpeed.KILOMETERS_PER_HOUR
    )
    assert state.attributes.get(ATTR_ICON) is None
    assert state.attributes.get(ATTR_STATE_CLASS) == SensorStateClass.MEASUREMENT
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.WIND_SPEED

    entry = registry.async_get("sensor.home_wind")
    assert entry
    assert entry.unique_id == "0123456-wind"

    state = hass.states.get("sensor.home_cloud_cover_day_0d")
    assert state
    assert state.state == "58"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == PERCENTAGE
    assert state.attributes.get(ATTR_ICON) == "mdi:weather-cloudy"
    assert state.attributes.get(ATTR_STATE_CLASS) is None

    entry = registry.async_get("sensor.home_cloud_cover_day_0d")
    assert entry
    assert entry.unique_id == "0123456-cloudcoverday-0"

    state = hass.states.get("sensor.home_cloud_cover_night_0d")
    assert state
    assert state.state == "65"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == PERCENTAGE
    assert state.attributes.get(ATTR_ICON) == "mdi:weather-cloudy"
    assert state.attributes.get(ATTR_STATE_CLASS) is None

    entry = registry.async_get("sensor.home_cloud_cover_night_0d")
    assert entry

    state = hass.states.get("sensor.home_grass_pollen_0d")
    assert state
    assert state.state == "0"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert (
        state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        == CONCENTRATION_PARTS_PER_CUBIC_METER
    )
    assert state.attributes.get("level") == "Low"
    assert state.attributes.get(ATTR_ICON) == "mdi:grass"
    assert state.attributes.get(ATTR_STATE_CLASS) is None

    entry = registry.async_get("sensor.home_grass_pollen_0d")
    assert entry
    assert entry.unique_id == "0123456-grass-0"

    state = hass.states.get("sensor.home_mold_pollen_0d")
    assert state
    assert state.state == "0"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert (
        state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        == CONCENTRATION_PARTS_PER_CUBIC_METER
    )
    assert state.attributes.get("level") == "Low"
    assert state.attributes.get(ATTR_ICON) == "mdi:blur"

    entry = registry.async_get("sensor.home_mold_pollen_0d")
    assert entry
    assert entry.unique_id == "0123456-mold-0"

    state = hass.states.get("sensor.home_ozone_0d")
    assert state
    assert state.state == "32"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert state.attributes.get("level") == "Good"
    assert state.attributes.get(ATTR_ICON) == "mdi:vector-triangle"
    assert state.attributes.get(ATTR_STATE_CLASS) is None

    entry = registry.async_get("sensor.home_ozone_0d")
    assert entry
    assert entry.unique_id == "0123456-ozone-0"

    state = hass.states.get("sensor.home_ragweed_pollen_0d")
    assert state
    assert state.state == "0"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert (
        state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        == CONCENTRATION_PARTS_PER_CUBIC_METER
    )
    assert state.attributes.get("level") == "Low"
    assert state.attributes.get(ATTR_ICON) == "mdi:sprout"

    entry = registry.async_get("sensor.home_ragweed_pollen_0d")
    assert entry
    assert entry.unique_id == "0123456-ragweed-0"

    state = hass.states.get("sensor.home_realfeel_temperature_shade_max_0d")
    assert state
    assert state.state == "28.0"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfTemperature.CELSIUS
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.TEMPERATURE
    assert state.attributes.get(ATTR_STATE_CLASS) is None

    entry = registry.async_get("sensor.home_realfeel_temperature_shade_max_0d")
    assert entry
    assert entry.unique_id == "0123456-realfeeltemperatureshademax-0"

    state = hass.states.get("sensor.home_realfeel_temperature_shade_min_0d")
    assert state
    assert state.state == "15.1"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfTemperature.CELSIUS
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.TEMPERATURE

    entry = registry.async_get("sensor.home_realfeel_temperature_shade_min_0d")
    assert entry
    assert entry.unique_id == "0123456-realfeeltemperatureshademin-0"

    state = hass.states.get("sensor.home_tree_pollen_0d")
    assert state
    assert state.state == "0"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert (
        state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        == CONCENTRATION_PARTS_PER_CUBIC_METER
    )
    assert state.attributes.get("level") == "Low"
    assert state.attributes.get(ATTR_ICON) == "mdi:tree-outline"
    assert state.attributes.get(ATTR_STATE_CLASS) is None

    entry = registry.async_get("sensor.home_tree_pollen_0d")
    assert entry
    assert entry.unique_id == "0123456-tree-0"

    state = hass.states.get("sensor.home_wind_day_0d")
    assert state
    assert state.state == "13.0"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert (
        state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        == UnitOfSpeed.KILOMETERS_PER_HOUR
    )
    assert state.attributes.get("direction") == "SSE"
    assert state.attributes.get(ATTR_ICON) is None
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.WIND_SPEED

    entry = registry.async_get("sensor.home_wind_day_0d")
    assert entry
    assert entry.unique_id == "0123456-windday-0"

    state = hass.states.get("sensor.home_wind_night_0d")
    assert state
    assert state.state == "7.4"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert (
        state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        == UnitOfSpeed.KILOMETERS_PER_HOUR
    )
    assert state.attributes.get("direction") == "WNW"
    assert state.attributes.get(ATTR_ICON) is None
    assert state.attributes.get(ATTR_STATE_CLASS) is None
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.WIND_SPEED

    entry = registry.async_get("sensor.home_wind_night_0d")
    assert entry
    assert entry.unique_id == "0123456-windnight-0"

    state = hass.states.get("sensor.home_wind_gust_day_0d")
    assert state
    assert state.state == "29.6"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert (
        state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        == UnitOfSpeed.KILOMETERS_PER_HOUR
    )
    assert state.attributes.get("direction") == "S"
    assert state.attributes.get(ATTR_ICON) is None
    assert state.attributes.get(ATTR_STATE_CLASS) is None
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.WIND_SPEED

    entry = registry.async_get("sensor.home_wind_gust_day_0d")
    assert entry
    assert entry.unique_id == "0123456-windgustday-0"

    state = hass.states.get("sensor.home_wind_gust_night_0d")
    assert state
    assert state.state == "18.5"
    assert state.attributes.get(ATTR_ATTRIBUTION) == ATTRIBUTION
    assert (
        state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        == UnitOfSpeed.KILOMETERS_PER_HOUR
    )
    assert state.attributes.get("direction") == "WSW"
    assert state.attributes.get(ATTR_ICON) is None
    assert state.attributes.get(ATTR_STATE_CLASS) is None
    assert state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.WIND_SPEED

    entry = registry.async_get("sensor.home_wind_gust_night_0d")
    assert entry
    assert entry.unique_id == "0123456-windgustnight-0"


async def test_availability(hass: HomeAssistant) -> None:
    """Ensure that we mark the entities unavailable correctly when service is offline."""
    await init_integration(hass)

    state = hass.states.get("sensor.home_cloud_ceiling")
    assert state
    assert state.state != STATE_UNAVAILABLE
    assert state.state == "3200.0"

    future = utcnow() + timedelta(minutes=60)
    with patch(
        "homeassistant.components.accuweather.AccuWeather.async_get_current_conditions",
        side_effect=ConnectionError(),
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

        state = hass.states.get("sensor.home_cloud_ceiling")
        assert state
        assert state.state == STATE_UNAVAILABLE

    future = utcnow() + timedelta(minutes=120)
    with patch(
        "homeassistant.components.accuweather.AccuWeather.async_get_current_conditions",
        return_value=load_json_object_fixture(
            "accuweather/current_conditions_data.json"
        ),
    ), patch(
        "homeassistant.components.accuweather.AccuWeather.requests_remaining",
        new_callable=PropertyMock,
        return_value=10,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

        state = hass.states.get("sensor.home_cloud_ceiling")
        assert state
        assert state.state != STATE_UNAVAILABLE
        assert state.state == "3200.0"


async def test_manual_update_entity(hass: HomeAssistant) -> None:
    """Test manual update entity via service homeassistant/update_entity."""
    await init_integration(hass, forecast=True)

    await async_setup_component(hass, "homeassistant", {})

    current = load_json_object_fixture("accuweather/current_conditions_data.json")
    forecast = load_json_array_fixture("accuweather/forecast_data.json")

    with patch(
        "homeassistant.components.accuweather.AccuWeather.async_get_current_conditions",
        return_value=current,
    ) as mock_current, patch(
        "homeassistant.components.accuweather.AccuWeather.async_get_forecast",
        return_value=forecast,
    ) as mock_forecast, patch(
        "homeassistant.components.accuweather.AccuWeather.requests_remaining",
        new_callable=PropertyMock,
        return_value=10,
    ):
        await hass.services.async_call(
            "homeassistant",
            "update_entity",
            {ATTR_ENTITY_ID: ["sensor.home_cloud_ceiling"]},
            blocking=True,
        )
        assert mock_current.call_count == 1
        assert mock_forecast.call_count == 1


async def test_sensor_imperial_units(hass: HomeAssistant) -> None:
    """Test states of the sensor without forecast."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    await init_integration(hass)

    state = hass.states.get("sensor.home_cloud_ceiling")
    assert state
    assert state.state == "10498.687664042"
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfLength.FEET

    state = hass.states.get("sensor.home_wind")
    assert state
    assert state.state == "9.0"
    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfSpeed.MILES_PER_HOUR

    state = hass.states.get("sensor.home_realfeel_temperature")
    assert state
    assert state.state == "77.2"
    assert (
        state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfTemperature.FAHRENHEIT
    )


async def test_state_update(hass: HomeAssistant) -> None:
    """Ensure the sensor state changes after updating the data."""
    await init_integration(hass)

    state = hass.states.get("sensor.home_cloud_ceiling")
    assert state
    assert state.state != STATE_UNAVAILABLE
    assert state.state == "3200.0"

    future = utcnow() + timedelta(minutes=60)

    current_condition = load_json_object_fixture(
        "accuweather/current_conditions_data.json"
    )
    current_condition["Ceiling"]["Metric"]["Value"] = 3300

    with patch(
        "homeassistant.components.accuweather.AccuWeather.async_get_current_conditions",
        return_value=current_condition,
    ), patch(
        "homeassistant.components.accuweather.AccuWeather.requests_remaining",
        new_callable=PropertyMock,
        return_value=10,
    ):
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()

        state = hass.states.get("sensor.home_cloud_ceiling")
        assert state
        assert state.state != STATE_UNAVAILABLE
        assert state.state == "3300"
