"""Support for Dexcom sensors."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_UNIT_OF_MEASUREMENT, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import COORDINATOR, DOMAIN, GLUCOSE_TREND_ICON, GLUCOSE_VALUE_ICON, MG_DL


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Dexcom sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    username = config_entry.data[CONF_USERNAME]
    unit_of_measurement = config_entry.options[CONF_UNIT_OF_MEASUREMENT]
    async_add_entities(
        [
            DexcomGlucoseTrendSensor(coordinator, username),
            DexcomGlucoseValueSensor(coordinator, username, unit_of_measurement),
        ],
        False,
    )


class DexcomGlucoseValueSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Dexcom glucose value sensor."""

    _attr_icon = GLUCOSE_VALUE_ICON

    def __init__(self, coordinator, username, unit_of_measurement):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_native_unit_of_measurement = unit_of_measurement
        self._key = "mg_dl" if unit_of_measurement == MG_DL else "mmol_l"
        self._attr_name = f"{DOMAIN}_{username}_glucose_value"
        self._attr_unique_id = f"{username}-value"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return getattr(self.coordinator.data, self._key)
        return None


class DexcomGlucoseTrendSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Dexcom glucose trend sensor."""

    def __init__(self, coordinator, username):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = f"{DOMAIN}_{username}_glucose_trend"
        self._attr_unique_id = f"{username}-trend"

    @property
    def icon(self):
        """Return the icon for the frontend."""
        if self.coordinator.data:
            return GLUCOSE_TREND_ICON[self.coordinator.data.trend]
        return GLUCOSE_TREND_ICON[0]

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.trend_description
        return None
