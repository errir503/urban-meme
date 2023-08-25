"""Support for Open-Meteo weather."""
from __future__ import annotations

from open_meteo import Forecast as OpenMeteoForecast

from homeassistant.components.weather import (
    Forecast,
    SingleCoordinatorWeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPrecipitationDepth, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, WMO_TO_HA_CONDITION_MAP


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Open-Meteo weather entity based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OpenMeteoWeatherEntity(entry=entry, coordinator=coordinator)])


class OpenMeteoWeatherEntity(
    SingleCoordinatorWeatherEntity[DataUpdateCoordinator[OpenMeteoForecast]]
):
    """Defines an Open-Meteo weather entity."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_supported_features = WeatherEntityFeature.FORECAST_DAILY

    def __init__(
        self,
        *,
        entry: ConfigEntry,
        coordinator: DataUpdateCoordinator[OpenMeteoForecast],
    ) -> None:
        """Initialize Open-Meteo weather entity."""
        super().__init__(coordinator=coordinator)
        self._attr_unique_id = entry.entry_id

        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="Open-Meteo",
            name=entry.title,
        )

    @property
    def condition(self) -> str | None:
        """Return the current condition."""
        if not self.coordinator.data.current_weather:
            return None
        return WMO_TO_HA_CONDITION_MAP.get(
            self.coordinator.data.current_weather.weather_code
        )

    @property
    def native_temperature(self) -> float | None:
        """Return the platform temperature."""
        if not self.coordinator.data.current_weather:
            return None
        return self.coordinator.data.current_weather.temperature

    @property
    def native_wind_speed(self) -> float | None:
        """Return the wind speed."""
        if not self.coordinator.data.current_weather:
            return None
        return self.coordinator.data.current_weather.wind_speed

    @property
    def wind_bearing(self) -> float | str | None:
        """Return the wind bearing."""
        if not self.coordinator.data.current_weather:
            return None
        return self.coordinator.data.current_weather.wind_direction

    @property
    def forecast(self) -> list[Forecast] | None:
        """Return the forecast in native units."""
        if self.coordinator.data.daily is None:
            return None

        forecasts: list[Forecast] = []
        daily = self.coordinator.data.daily
        for index, time in enumerate(self.coordinator.data.daily.time):
            forecast = Forecast(
                datetime=time.isoformat(),
            )

            if daily.weathercode is not None:
                forecast["condition"] = WMO_TO_HA_CONDITION_MAP.get(
                    daily.weathercode[index]
                )

            if daily.precipitation_sum is not None:
                forecast["native_precipitation"] = daily.precipitation_sum[index]

            if daily.temperature_2m_max is not None:
                forecast["native_temperature"] = daily.temperature_2m_max[index]

            if daily.temperature_2m_min is not None:
                forecast["native_templow"] = daily.temperature_2m_min[index]

            if daily.wind_direction_10m_dominant is not None:
                forecast["wind_bearing"] = daily.wind_direction_10m_dominant[index]

            if daily.wind_speed_10m_max is not None:
                forecast["native_wind_speed"] = daily.wind_speed_10m_max[index]

            forecasts.append(forecast)

        return forecasts

    @callback
    def _async_forecast_daily(self) -> list[Forecast] | None:
        """Return the daily forecast in native units."""
        return self.forecast
