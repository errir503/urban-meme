"""Support for GoodWe inverter via UDP."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any, cast

from goodwe import Inverter, Sensor, SensorKind

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ELECTRIC_CURRENT_AMPERE,
    ELECTRIC_POTENTIAL_VOLT,
    ENERGY_KILO_WATT_HOUR,
    FREQUENCY_HERTZ,
    PERCENTAGE,
    POWER_WATT,
    TEMP_CELSIUS,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
import homeassistant.util.dt as dt_util

from .const import DOMAIN, KEY_COORDINATOR, KEY_DEVICE_INFO, KEY_INVERTER

_LOGGER = logging.getLogger(__name__)

# Sensor name of battery SoC
BATTERY_SOC = "battery_soc"

# Sensors that are reset to 0 at midnight.
# The inverter is only powered by the solar panels and not mains power, so it goes dead when the sun goes down.
# The "_day" sensors are reset to 0 when the inverter wakes up in the morning when the sun comes up and power to the inverter is restored.
# This makes sure daily values are reset at midnight instead of at sunrise.
# When the inverter has a battery connected, HomeAssistant will not reset the values but let the inverter reset them by looking at the unavailable state of the inverter.
DAILY_RESET = ["e_day", "e_load_day"]

_MAIN_SENSORS = (
    "ppv",
    "house_consumption",
    "active_power",
    "battery_soc",
    "e_day",
    "e_total",
    "meter_e_total_exp",
    "meter_e_total_imp",
    "e_bat_charge_total",
    "e_bat_discharge_total",
)

_ICONS: dict[SensorKind, str] = {
    SensorKind.PV: "mdi:solar-power",
    SensorKind.AC: "mdi:power-plug-outline",
    SensorKind.UPS: "mdi:power-plug-off-outline",
    SensorKind.BAT: "mdi:battery-high",
    SensorKind.GRID: "mdi:transmission-tower",
}


@dataclass
class GoodweSensorEntityDescription(SensorEntityDescription):
    """Class describing Goodwe sensor entities."""

    value: Callable[[Any, Any], Any] = lambda prev, val: val
    available: Callable[
        [CoordinatorEntity], bool
    ] = lambda entity: entity.coordinator.last_update_success


_DESCRIPTIONS: dict[str, GoodweSensorEntityDescription] = {
    "A": GoodweSensorEntityDescription(
        key="A",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
    ),
    "V": GoodweSensorEntityDescription(
        key="V",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=ELECTRIC_POTENTIAL_VOLT,
    ),
    "W": GoodweSensorEntityDescription(
        key="W",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=POWER_WATT,
    ),
    "kWh": GoodweSensorEntityDescription(
        key="kWh",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        value=lambda prev, val: prev if not val else val,
        available=lambda entity: entity.coordinator.data is not None,
    ),
    "C": GoodweSensorEntityDescription(
        key="C",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=TEMP_CELSIUS,
    ),
    "Hz": GoodweSensorEntityDescription(
        key="Hz",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=FREQUENCY_HERTZ,
    ),
    "%": GoodweSensorEntityDescription(
        key="%",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
}
DIAG_SENSOR = GoodweSensorEntityDescription(
    key="_",
    state_class=SensorStateClass.MEASUREMENT,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the GoodWe inverter from a config entry."""
    entities: list[InverterSensor] = []
    inverter = hass.data[DOMAIN][config_entry.entry_id][KEY_INVERTER]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][KEY_COORDINATOR]
    device_info = hass.data[DOMAIN][config_entry.entry_id][KEY_DEVICE_INFO]

    # Individual inverter sensors entities
    entities.extend(
        InverterSensor(coordinator, device_info, inverter, sensor)
        for sensor in inverter.sensors()
        if not sensor.id_.startswith("xx")
    )

    async_add_entities(entities)


class InverterSensor(CoordinatorEntity, SensorEntity):
    """Entity representing individual inverter sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_info: DeviceInfo,
        inverter: Inverter,
        sensor: Sensor,
    ) -> None:
        """Initialize an inverter sensor."""
        super().__init__(coordinator)
        self._attr_name = sensor.name.strip()
        self._attr_unique_id = f"{DOMAIN}-{sensor.id_}-{inverter.serial_number}"
        self._attr_device_info = device_info
        self._attr_entity_category = (
            EntityCategory.DIAGNOSTIC if sensor.id_ not in _MAIN_SENSORS else None
        )
        self.entity_description = _DESCRIPTIONS.get(sensor.unit, DIAG_SENSOR)
        if not self.entity_description.native_unit_of_measurement:
            self._attr_native_unit_of_measurement = sensor.unit
        self._attr_icon = _ICONS.get(sensor.kind)
        # Set the inverter SoC as main device battery sensor
        if sensor.id_ == BATTERY_SOC:
            self._attr_device_class = SensorDeviceClass.BATTERY
        self._sensor = sensor
        self._previous_value = None
        self._stop_reset = None

    @property
    def native_value(self):
        """Return the value reported by the sensor."""
        value = cast(GoodweSensorEntityDescription, self.entity_description).value(
            self._previous_value,
            self.coordinator.data.get(self._sensor.id_, self._previous_value),
        )
        self._previous_value = value
        return value

    @property
    def available(self) -> bool:
        """Return if entity is available.

        We delegate the behavior to entity description lambda, since
        some sensors (like energy produced today) should report themselves
        as available even when the (non-battery) pv inverter is off-line during night
        and most of the sensors are actually unavailable.
        """
        return cast(GoodweSensorEntityDescription, self.entity_description).available(
            self
        )

    @callback
    def async_reset(self, now):
        """Reset the value back to 0 at midnight."""
        if not self.coordinator.last_update_success:
            self._previous_value = 0
            self.coordinator.data[self._sensor.id_] = 0
            self.async_write_ha_state()
            _LOGGER.debug("Goodwe reset %s to 0", self.name)
        next_midnight = dt_util.start_of_local_day(
            dt_util.now() + timedelta(days=1, minutes=1)
        )
        self._stop_reset = async_track_point_in_time(
            self.hass, self.async_reset, next_midnight
        )

    async def async_added_to_hass(self):
        """Schedule reset task at midnight."""
        if self._sensor.id_ in DAILY_RESET:
            next_midnight = dt_util.start_of_local_day(
                dt_util.now() + timedelta(days=1)
            )
            self._stop_reset = async_track_point_in_time(
                self.hass, self.async_reset, next_midnight
            )
        await super().async_added_to_hass()

    async def async_will_remove_from_hass(self):
        """Remove reset task at midnight."""
        if self._sensor.id_ in DAILY_RESET and self._stop_reset is not None:
            self._stop_reset()
        await super().async_will_remove_from_hass()
