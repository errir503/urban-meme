"""Sensor to collect the reference daily prices of electricity ('PVPC') in Spain."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, CURRENCY_EURO, ENERGY_KILO_WATT_HOUR
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ElecPricesDataUpdateCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 1
SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="PVPC",
        icon="mdi:currency-eur",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=SensorStateClass.MEASUREMENT,
    ),
)
_PRICE_SENSOR_ATTRIBUTES_MAP = {
    "tariff": "tariff",
    "period": "period",
    "available_power": "available_power",
    "next_period": "next_period",
    "hours_to_next_period": "hours_to_next_period",
    "next_better_price": "next_better_price",
    "hours_to_better_price": "hours_to_better_price",
    "num_better_prices_ahead": "num_better_prices_ahead",
    "price_position": "price_position",
    "price_ratio": "price_ratio",
    "max_price": "max_price",
    "max_price_at": "max_price_at",
    "min_price": "min_price",
    "min_price_at": "min_price_at",
    "next_best_at": "next_best_at",
    "price_00h": "price_00h",
    "price_01h": "price_01h",
    "price_02h": "price_02h",
    "price_02h_d": "price_02h_d",  # only on DST day change with 25h
    "price_03h": "price_03h",
    "price_04h": "price_04h",
    "price_05h": "price_05h",
    "price_06h": "price_06h",
    "price_07h": "price_07h",
    "price_08h": "price_08h",
    "price_09h": "price_09h",
    "price_10h": "price_10h",
    "price_11h": "price_11h",
    "price_12h": "price_12h",
    "price_13h": "price_13h",
    "price_14h": "price_14h",
    "price_15h": "price_15h",
    "price_16h": "price_16h",
    "price_17h": "price_17h",
    "price_18h": "price_18h",
    "price_19h": "price_19h",
    "price_20h": "price_20h",
    "price_21h": "price_21h",
    "price_22h": "price_22h",
    "price_23h": "price_23h",
    # only seen in the evening
    "next_better_price (next day)": "next_better_price (next day)",
    "hours_to_better_price (next day)": "hours_to_better_price (next day)",
    "num_better_prices_ahead (next day)": "num_better_prices_ahead (next day)",
    "price_position (next day)": "price_position (next day)",
    "price_ratio (next day)": "price_ratio (next day)",
    "max_price (next day)": "max_price (next day)",
    "max_price_at (next day)": "max_price_at (next day)",
    "min_price (next day)": "min_price (next day)",
    "min_price_at (next day)": "min_price_at (next day)",
    "next_best_at (next day)": "next_best_at (next day)",
    "price_next_day_00h": "price_next_day_00h",
    "price_next_day_01h": "price_next_day_01h",
    "price_next_day_02h": "price_next_day_02h",
    "price_next_day_02h_d": "price_next_day_02h_d",
    "price_next_day_03h": "price_next_day_03h",
    "price_next_day_04h": "price_next_day_04h",
    "price_next_day_05h": "price_next_day_05h",
    "price_next_day_06h": "price_next_day_06h",
    "price_next_day_07h": "price_next_day_07h",
    "price_next_day_08h": "price_next_day_08h",
    "price_next_day_09h": "price_next_day_09h",
    "price_next_day_10h": "price_next_day_10h",
    "price_next_day_11h": "price_next_day_11h",
    "price_next_day_12h": "price_next_day_12h",
    "price_next_day_13h": "price_next_day_13h",
    "price_next_day_14h": "price_next_day_14h",
    "price_next_day_15h": "price_next_day_15h",
    "price_next_day_16h": "price_next_day_16h",
    "price_next_day_17h": "price_next_day_17h",
    "price_next_day_18h": "price_next_day_18h",
    "price_next_day_19h": "price_next_day_19h",
    "price_next_day_20h": "price_next_day_20h",
    "price_next_day_21h": "price_next_day_21h",
    "price_next_day_22h": "price_next_day_22h",
    "price_next_day_23h": "price_next_day_23h",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the electricity price sensor from config_entry."""
    coordinator: ElecPricesDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    name = entry.data[CONF_NAME]
    async_add_entities(
        [ElecPriceSensor(coordinator, SENSOR_TYPES[0], entry.unique_id, name)]
    )


class ElecPriceSensor(CoordinatorEntity[ElecPricesDataUpdateCoordinator], SensorEntity):
    """Class to hold the prices of electricity as a sensor."""

    def __init__(
        self,
        coordinator: ElecPricesDataUpdateCoordinator,
        description: SensorEntityDescription,
        unique_id: str | None,
        name: str,
    ) -> None:
        """Initialize ESIOS sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_attribution = coordinator.api.attribution
        self._attr_unique_id = unique_id
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            configuration_url="https://www.ree.es/es/apidatos",
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, coordinator.entry_id)},
            manufacturer="REE",
            name="PVPC (REData API)",
        )
        self._state: StateType = None
        self._attrs: Mapping[str, Any] = {}

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()

        # Update 'state' value in hour changes
        self.async_on_remove(
            async_track_time_change(
                self.hass, self.update_current_price, second=[0], minute=[0]
            )
        )
        _LOGGER.debug(
            "Setup of price sensor %s (%s) with tariff '%s'",
            self.name,
            self.entity_id,
            self.coordinator.api.tariff,
        )

    @callback
    def update_current_price(self, now: datetime) -> None:
        """Update the sensor state, by selecting the current price for this hour."""
        self.coordinator.api.process_state_and_attributes(now)
        self.async_write_ha_state()

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        self._state = self.coordinator.api.state
        return self._state

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return the state attributes."""
        self._attrs = {
            _PRICE_SENSOR_ATTRIBUTES_MAP[key]: value
            for key, value in self.coordinator.api.attributes.items()
            if key in _PRICE_SENSOR_ATTRIBUTES_MAP
        }
        return self._attrs
