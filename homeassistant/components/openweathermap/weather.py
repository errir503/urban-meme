"""Support for the OpenWeatherMap (OWM) service."""
from __future__ import annotations

from typing import cast

from homeassistant.components.weather import (
    ATTR_FORECAST_CONDITION,
    ATTR_FORECAST_NATIVE_PRECIPITATION,
    ATTR_FORECAST_NATIVE_PRESSURE,
    ATTR_FORECAST_NATIVE_TEMP,
    ATTR_FORECAST_NATIVE_TEMP_LOW,
    ATTR_FORECAST_NATIVE_WIND_SPEED,
    ATTR_FORECAST_PRECIPITATION_PROBABILITY,
    ATTR_FORECAST_TIME,
    ATTR_FORECAST_WIND_BEARING,
    Forecast,
    WeatherEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    LENGTH_MILLIMETERS,
    PRESSURE_HPA,
    SPEED_METERS_PER_SECOND,
    TEMP_CELSIUS,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_API_CONDITION,
    ATTR_API_FORECAST,
    ATTR_API_FORECAST_CONDITION,
    ATTR_API_FORECAST_PRECIPITATION,
    ATTR_API_FORECAST_PRECIPITATION_PROBABILITY,
    ATTR_API_FORECAST_PRESSURE,
    ATTR_API_FORECAST_TEMP,
    ATTR_API_FORECAST_TEMP_LOW,
    ATTR_API_FORECAST_TIME,
    ATTR_API_FORECAST_WIND_BEARING,
    ATTR_API_FORECAST_WIND_SPEED,
    ATTR_API_HUMIDITY,
    ATTR_API_PRESSURE,
    ATTR_API_TEMPERATURE,
    ATTR_API_WIND_BEARING,
    ATTR_API_WIND_SPEED,
    ATTRIBUTION,
    DEFAULT_NAME,
    DOMAIN,
    ENTRY_NAME,
    ENTRY_WEATHER_COORDINATOR,
    MANUFACTURER,
)
from .weather_update_coordinator import WeatherUpdateCoordinator

FORECAST_MAP = {
    ATTR_API_FORECAST_CONDITION: ATTR_FORECAST_CONDITION,
    ATTR_API_FORECAST_PRECIPITATION: ATTR_FORECAST_NATIVE_PRECIPITATION,
    ATTR_API_FORECAST_PRECIPITATION_PROBABILITY: ATTR_FORECAST_PRECIPITATION_PROBABILITY,
    ATTR_API_FORECAST_PRESSURE: ATTR_FORECAST_NATIVE_PRESSURE,
    ATTR_API_FORECAST_TEMP_LOW: ATTR_FORECAST_NATIVE_TEMP_LOW,
    ATTR_API_FORECAST_TEMP: ATTR_FORECAST_NATIVE_TEMP,
    ATTR_API_FORECAST_TIME: ATTR_FORECAST_TIME,
    ATTR_API_FORECAST_WIND_BEARING: ATTR_FORECAST_WIND_BEARING,
    ATTR_API_FORECAST_WIND_SPEED: ATTR_FORECAST_NATIVE_WIND_SPEED,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up OpenWeatherMap weather entity based on a config entry."""
    domain_data = hass.data[DOMAIN][config_entry.entry_id]
    name = domain_data[ENTRY_NAME]
    weather_coordinator = domain_data[ENTRY_WEATHER_COORDINATOR]

    unique_id = f"{config_entry.unique_id}"
    owm_weather = OpenWeatherMapWeather(name, unique_id, weather_coordinator)

    async_add_entities([owm_weather], False)


class OpenWeatherMapWeather(WeatherEntity):
    """Implementation of an OpenWeatherMap sensor."""

    _attr_attribution = ATTRIBUTION
    _attr_should_poll = False

    _attr_native_precipitation_unit = LENGTH_MILLIMETERS
    _attr_native_pressure_unit = PRESSURE_HPA
    _attr_native_temperature_unit = TEMP_CELSIUS
    _attr_native_wind_speed_unit = SPEED_METERS_PER_SECOND

    def __init__(
        self,
        name: str,
        unique_id: str,
        weather_coordinator: WeatherUpdateCoordinator,
    ) -> None:
        """Initialize the sensor."""
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, unique_id)},
            manufacturer=MANUFACTURER,
            name=DEFAULT_NAME,
        )
        self._weather_coordinator = weather_coordinator

    @property
    def condition(self) -> str | None:
        """Return the current condition."""
        return self._weather_coordinator.data[ATTR_API_CONDITION]

    @property
    def native_temperature(self) -> float | None:
        """Return the temperature."""
        return self._weather_coordinator.data[ATTR_API_TEMPERATURE]

    @property
    def native_pressure(self) -> float | None:
        """Return the pressure."""
        return self._weather_coordinator.data[ATTR_API_PRESSURE]

    @property
    def humidity(self) -> float | None:
        """Return the humidity."""
        return self._weather_coordinator.data[ATTR_API_HUMIDITY]

    @property
    def native_wind_speed(self) -> float | None:
        """Return the wind speed."""
        return self._weather_coordinator.data[ATTR_API_WIND_SPEED]

    @property
    def wind_bearing(self) -> float | str | None:
        """Return the wind bearing."""
        return self._weather_coordinator.data[ATTR_API_WIND_BEARING]

    @property
    def forecast(self) -> list[Forecast] | None:
        """Return the forecast array."""
        api_forecasts = self._weather_coordinator.data[ATTR_API_FORECAST]
        forecasts = [
            {
                ha_key: forecast[api_key]
                for api_key, ha_key in FORECAST_MAP.items()
                if api_key in forecast
            }
            for forecast in api_forecasts
        ]
        return cast(list[Forecast], forecasts)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._weather_coordinator.last_update_success

    async def async_added_to_hass(self) -> None:
        """Connect to dispatcher listening for entity data notifications."""
        self.async_on_remove(
            self._weather_coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self) -> None:
        """Get the latest data from OWM and updates the states."""
        await self._weather_coordinator.async_request_refresh()
